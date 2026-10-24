"""HTTP adapter: POSTs the case input to a configured endpoint (ADAPTER_ISOLATION.md s4, D-015).

Everything the endpoint sends back is untrusted data. Safety properties:
- the URL comes only from the local config (never from cases/traces); host must be loopback or
  explicitly allow-listed; https unless loopback or ``allow_insecure_http``;
- SSRF guard: the host is resolved ONCE, every resolved address is checked, and the connection is
  pinned to the validated address (no second lookup, so no DNS rebinding). Link-local (cloud
  metadata), unspecified, multicast and reserved addresses are always refused; non-loopback
  addresses are refused unless the host is allow-listed;
- redirects are never followed; TLS certificates and host names are always verified;
- the response is read incrementally with a byte cap, and a watchdog enforces ONE total deadline
  (a trickling server cannot extend it). DNS lookup time is not covered by the deadline;
- credentials come from environment variables named in ``headers_env``; values are never stored,
  logged or echoed in errors;
- every failure raises ``AdapterError`` (the engine records it as a failed run).
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import ssl
import threading
import time
from collections.abc import Mapping
from typing import Any

from . import __version__
from .config import HttpAdapterConfig
from .models import RunMetadata
from .subprocess_adapter import SNIPPET_BYTES, AdapterError, _parse_output

_CHUNK = 65536


class _PinnedConnection(http.client.HTTPConnection):
    """Connects to an already validated IP; TLS (if any) still verifies the real host name."""

    def __init__(self, host: str, port: int, ip: str, tls: ssl.SSLContext | None, remaining) -> None:
        super().__init__(host, port)
        self._ip = ip
        self._tls = tls
        self._remaining = remaining
        # http.client hands ``sock`` to the response and sets ``self.sock = None`` for
        # "Connection: close" replies, so the watchdog needs its own reference.
        self.raw_sock: socket.socket | None = None

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), max(self._remaining(), 0.001))
        if self._tls is not None:
            try:
                sock = self._tls.wrap_socket(sock, server_hostname=self.host)
            except BaseException:
                sock.close()
                raise
        self.sock = sock
        self.raw_sock = sock


class HttpAdapter:
    """Implements the ``AgentRunner`` protocol by calling a configured HTTP endpoint once."""

    def __init__(self, config: HttpAdapterConfig, environ: Mapping[str, str] | None = None) -> None:
        self._config = config
        self._environ: Mapping[str, str] = os.environ if environ is None else environ
        self.last_metadata: RunMetadata | None = None

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        cfg = self._config
        meta: dict[str, Any] = {
            "adapter_name": cfg.name,
            "adapter_tier": "H",
            "argv": ["POST", cfg.url],
            "env_names": [env for _, env in cfg.headers_env],
            "timeout_seconds": float(cfg.timeout_seconds),
            "limits": {"max_response_bytes": cfg.max_response_bytes},
        }
        self.last_metadata = RunMetadata(**meta)
        start = time.monotonic()
        try:
            return self._run(input_data, meta, start)
        finally:
            meta["duration_ms"] = int((time.monotonic() - start) * 1000)
            self.last_metadata = RunMetadata(**meta)

    # ------------------------------------------------------------------ internals
    def _run(self, input_data: dict[str, Any], meta: dict[str, Any], start: float) -> dict[str, Any]:
        cfg = self._config
        deadline = start + cfg.timeout_seconds
        headers = self._headers()
        try:
            body = json.dumps(input_data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError):
            raise AdapterError("case input is not JSON-serializable") from None
        ip = self._resolve()
        tls = ssl.create_default_context() if cfg.scheme == "https" else None

        def remaining() -> float:
            return deadline - time.monotonic()

        conn = _PinnedConnection(cfg.host, cfg.port, ip, tls, remaining)
        expired = threading.Event()

        def expire() -> None:
            expired.set()
            sock = conn.raw_sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

        watchdog = threading.Timer(max(remaining(), 0.001), expire)
        watchdog.daemon = True
        watchdog.start()
        try:
            conn.request("POST", cfg.path, body=body, headers=headers)
            if conn.sock is not None:
                conn.sock.settimeout(max(remaining(), 0.001))
            response = conn.getresponse()
            meta["exit_code"] = response.status
            raw = self._read_body(response, meta, remaining)
            if expired.is_set():  # the watchdog cut the connection: EOF looks like a short body
                raise AdapterError("deadline passed")
            return self._interpret(response.status, raw)
        except AdapterError:
            if expired.is_set():
                raise AdapterError(f"timed out after {cfg.timeout_seconds:g}s") from None
            raise
        except ssl.SSLError as exc:
            raise AdapterError(f"TLS error: {exc.reason or type(exc).__name__}") from None
        except (TimeoutError, OSError, http.client.HTTPException, ValueError) as exc:
            if expired.is_set() or isinstance(exc, TimeoutError):
                raise AdapterError(f"timed out after {cfg.timeout_seconds:g}s") from None
            raise AdapterError(f"connection failed: {type(exc).__name__}") from None
        finally:
            watchdog.cancel()
            conn.close()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"regressagent/{__version__}",
            "Connection": "close",
        }
        for header, env in self._config.headers_env:
            value = self._environ.get(env)
            if not value:
                raise AdapterError(f"environment variable {env} is not set or empty")
            if any(c in value for c in "\r\n\0") or not value.isascii():
                raise AdapterError(f"environment variable {env} holds an invalid header value")
            headers[header] = value
        return headers

    def _resolve(self) -> str:
        """Resolve once, check every address, return the one to connect to (the SSRF guard)."""
        cfg = self._config
        try:
            infos = socket.getaddrinfo(cfg.host, cfg.port, type=socket.SOCK_STREAM)
        except (OSError, UnicodeError):
            raise AdapterError("cannot resolve host") from None
        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for info in infos:
            try:
                ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
            except ValueError:
                raise AdapterError("cannot resolve host") from None
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
                ip = ip.ipv4_mapped
            addresses.append(ip)
        if not addresses:
            raise AdapterError("cannot resolve host")
        explicit = cfg.host in cfg.allow_hosts
        for ip in addresses:
            if ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
                raise AdapterError(
                    f"address {ip} refused (link-local, unspecified, multicast or reserved)"
                )
            if not explicit and not ip.is_loopback:
                raise AdapterError(
                    f"host resolved to non-loopback address {ip}; add the host to allow_hosts "
                    "if this is intended"
                )
        return str(addresses[0])

    def _read_body(self, response: http.client.HTTPResponse, meta: dict[str, Any], remaining) -> bytes:
        cap = self._config.max_response_bytes
        declared = response.getheader("Content-Length")
        if declared is not None and declared.isdigit() and int(declared) > cap:
            meta["stdout_truncated"] = True
            raise AdapterError(f"response exceeds {cap} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            if remaining() <= 0:
                raise AdapterError("deadline passed")
            chunk = response.read(min(_CHUNK, cap + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > cap:
                meta["stdout_truncated"] = True
                raise AdapterError(f"response exceeds {cap} bytes")
        return b"".join(chunks)

    @staticmethod
    def _interpret(status: int, raw: bytes) -> dict[str, Any]:
        if 300 <= status < 400:
            raise AdapterError(f"redirect not followed (HTTP {status})")
        if not 200 <= status < 300:
            snippet = raw[:SNIPPET_BYTES].decode("utf-8", errors="replace")
            snippet = "".join(c if c.isprintable() else " " for c in snippet).strip()
            raise AdapterError(f"HTTP {status}" + (f": {snippet}" if snippet else ""))
        return _parse_output(raw, what="response")


__all__ = ["HttpAdapter"]
