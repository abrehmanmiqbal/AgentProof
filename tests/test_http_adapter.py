"""HttpAdapter against a local hostile server. Everything the server sends is untrusted data;
every failure must become an AdapterError (a recorded failed run), never a hang or a crash."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agentproof import http_adapter
from agentproof.config import load_config
from agentproof.http_adapter import HttpAdapter
from agentproof.subprocess_adapter import AdapterError


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _send(self, status, body: bytes, headers=()):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        path = self.path
        if path == "/ok":
            self._send(200, json.dumps({"status": "ok", "echo": json.loads(body)}).encode())
        elif path == "/headers":
            seen = {"auth": self.headers.get("Authorization"), "ctype": self.headers.get("Content-Type"),
                    "host": self.headers.get("Host"), "ua": self.headers.get("User-Agent")}  # fmt: skip
            self._send(200, json.dumps(seen).encode())
        elif path == "/500":
            self._send(500, b"oops <b>secret-ish</b>")
        elif path == "/302":
            self._send(302, b"", [("Location", "/ok")])
        elif path == "/204":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/badjson":
            self._send(200, b"not json")
        elif path == "/array":
            self._send(200, b"[1]")
        elif path == "/nan":
            self._send(200, b'{"n": NaN}')
        elif path == "/utf8":
            self._send(200, b"\xff\xfe")
        elif path == "/deep":
            self._send(200, b'{"a":' * 100 + b"1" + b"}" * 100)
        elif path == "/claimed":  # claims a huge body, sends little
            self.send_response(200)
            self.send_header("Content-Length", "99999999")
            self.end_headers()
            self.wfile.write(b'{"a": 1}')
        elif path == "/huge":  # no Content-Length: stream until the client gives up
            self.send_response(200)
            self.end_headers()
            try:
                for _ in range(300):
                    self.wfile.write(b"a" * 10_000)
            except OSError:
                pass
        elif path == "/slow":  # trickles bytes forever
            self.send_response(200)
            self.end_headers()
            try:
                self.wfile.write(b'{"k": "')
                for _ in range(100):
                    time.sleep(0.2)
                    self.wfile.write(b"a")
                    self.wfile.flush()
            except OSError:
                pass
        elif path == "/hang":  # accepts the request, never answers
            time.sleep(5)
        elif path == "/close":
            self.close_connection = True
        else:
            self._send(404, b"{}")


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def make(tmp_path, url, extra="", headers="", environ=None):
    f = tmp_path / "agentproof.toml"
    f.write_text(f'[adapters.web]\ntype = "http"\nurl = "{url}"\n{extra}\n{headers}', encoding="utf-8")
    f.chmod(0o600)
    return HttpAdapter(load_config(f).adapters["web"], environ=environ or {})


# ---------------------------------------------------------------- happy path + metadata
def test_posts_the_input_as_json_and_returns_the_object(tmp_path, server):
    adapter = make(tmp_path, server + "/ok")
    assert adapter.run({"q": "hi"}) == {"status": "ok", "echo": {"q": "hi"}}
    meta = adapter.last_metadata
    assert meta.adapter_name == "web" and meta.adapter_tier == "H"
    assert meta.argv == ["POST", server + "/ok"] and meta.exit_code == 200
    assert meta.duration_ms is not None and meta.response_truncated is not True
    assert meta.limits == {"max_response_bytes": 1_000_000}
    assert meta.executable_path is None and meta.executable_sha256 is None


def test_request_headers_and_credentials_from_the_environment(tmp_path, server):
    headers = '[adapters.web.headers_env]\nAuthorization = "MY_TOKEN"\n'
    adapter = make(tmp_path, server + "/headers", headers=headers, environ={"MY_TOKEN": "Bearer s3cr3t-value"})
    out = adapter.run({})
    assert out["auth"] == "Bearer s3cr3t-value" and out["ctype"] == "application/json"
    assert out["host"].startswith("127.0.0.1:") and out["ua"].startswith("agentproof")
    stored = adapter.last_metadata.model_dump_json()
    assert "s3cr3t-value" not in stored and "MY_TOKEN" in stored  # names only, never values


@pytest.mark.parametrize("value", [None, "", "bad\r\nX-Injected: 1"])
def test_missing_or_malformed_credential_env_fails_without_leaking(tmp_path, server, value):
    headers = '[adapters.web.headers_env]\nAuthorization = "MY_TOKEN"\n'
    environ = {} if value is None else {"MY_TOKEN": value}
    adapter = make(tmp_path, server + "/ok", headers=headers, environ=environ)
    with pytest.raises(AdapterError, match="MY_TOKEN") as exc:
        adapter.run({})
    assert "X-Injected" not in str(exc.value)


# ---------------------------------------------------------------- hostile responses
@pytest.mark.parametrize(
    ("path", "needle"),
    [
        ("/500", "HTTP 500"),
        ("/302", "redirect"),
        ("/204", "JSON"),
        ("/badjson", "JSON"),
        ("/array", "object"),
        ("/nan", "JSON"),
        ("/utf8", "UTF-8"),
        ("/deep", "nested"),
        ("/404", "HTTP 404"),
        ("/close", "connection"),
    ],
)
def test_bad_responses_become_adapter_errors(tmp_path, server, path, needle):
    adapter = make(tmp_path, server + path)
    with pytest.raises(AdapterError, match=needle):
        adapter.run({})
    assert adapter.last_metadata is not None  # set even though the run failed


def test_redirects_are_never_followed(tmp_path, server):
    adapter = make(tmp_path, server + "/302")
    with pytest.raises(AdapterError, match="redirect"):
        adapter.run({})
    assert adapter.last_metadata.exit_code == 302


def test_error_body_snippet_is_short_and_printable(tmp_path, server):
    adapter = make(tmp_path, server + "/500")
    with pytest.raises(AdapterError) as exc:
        adapter.run({})
    assert len(str(exc.value)) < 400


def test_response_size_cap_stops_a_stream_without_content_length(tmp_path, server):
    adapter = make(tmp_path, server + "/huge", extra="max_response_bytes = 50000")
    start = time.monotonic()
    with pytest.raises(AdapterError, match="exceeds"):
        adapter.run({})
    assert time.monotonic() - start < 3
    assert adapter.last_metadata.response_truncated is True


def test_declared_oversize_is_refused_up_front(tmp_path, server):
    adapter = make(tmp_path, server + "/claimed", extra="max_response_bytes = 50000")
    with pytest.raises(AdapterError, match="exceeds"):
        adapter.run({})


def test_total_deadline_applies_to_trickling_responses(tmp_path, server):
    adapter = make(tmp_path, server + "/slow", extra="timeout_seconds = 1")
    start = time.monotonic()
    with pytest.raises(AdapterError, match="timed out"):
        adapter.run({})
    assert time.monotonic() - start < 2.5  # not 20 s: the deadline is total, not per read


def test_server_that_never_answers_times_out(tmp_path, server):
    adapter = make(tmp_path, server + "/hang", extra="timeout_seconds = 1")
    start = time.monotonic()
    with pytest.raises(AdapterError, match="timed out"):
        adapter.run({})
    assert time.monotonic() - start < 2.5


def test_connection_refused_is_a_clean_error(tmp_path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # nothing listens here now
    adapter = make(tmp_path, f"http://127.0.0.1:{port}/ok")
    with pytest.raises(AdapterError, match="connect"):
        adapter.run({})


def test_adapter_can_be_reused_and_metadata_tracks_the_latest_run(tmp_path, server):
    adapter = make(tmp_path, server + "/ok")
    adapter.run({"n": 1})
    first = adapter.last_metadata
    adapter.run({"n": 2})
    assert adapter.last_metadata is not first and adapter.last_metadata.exit_code == 200


# ---------------------------------------------------------------- SSRF guard (DNS is faked)
def fake_dns(monkeypatch, *addresses):
    def getaddrinfo(host, port, *args, **kwargs):
        family = lambda a: socket.AF_INET6 if ":" in a else socket.AF_INET
        return [(family(a), socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]

    monkeypatch.setattr(http_adapter.socket, "getaddrinfo", getaddrinfo)

    def no_connect(*args, **kwargs):
        raise ConnectionRefusedError("test: no real connection")

    monkeypatch.setattr(http_adapter.socket, "create_connection", no_connect)


ALLOW = 'allow_hosts = ["agent.internal"]\nallow_insecure_http = true\n'


@pytest.mark.parametrize(
    "address",
    ["169.254.169.254", "169.254.1.1", "fe80::1", "0.0.0.0", "::", "224.0.0.1", "ff02::1", "::ffff:169.254.169.254", "240.0.0.1"],
)
def test_always_refused_address_classes_even_for_allow_listed_hosts(tmp_path, monkeypatch, address):
    fake_dns(monkeypatch, address)
    adapter = make(tmp_path, "http://agent.internal/x", extra=ALLOW)
    with pytest.raises(AdapterError, match="refused"):
        adapter.run({})


def test_one_bad_address_among_good_ones_refuses_the_host(tmp_path, monkeypatch):
    fake_dns(monkeypatch, "10.0.0.5", "169.254.169.254")
    adapter = make(tmp_path, "http://agent.internal/x", extra=ALLOW)
    with pytest.raises(AdapterError, match="refused"):
        adapter.run({})


def test_localhost_must_really_resolve_to_loopback(tmp_path, monkeypatch):
    fake_dns(monkeypatch, "10.0.0.5")  # e.g. a tampered hosts file
    adapter = make(tmp_path, "http://localhost:8000/x")
    with pytest.raises(AdapterError, match="loopback"):
        adapter.run({})


def test_allow_listed_private_hosts_are_allowed_to_connect(tmp_path, monkeypatch):
    fake_dns(monkeypatch, "10.0.0.5")
    adapter = make(tmp_path, "http://agent.internal/x", extra=ALLOW)
    with pytest.raises(AdapterError, match="connect"):  # got past the guard, "network" refused
        adapter.run({})


def test_unresolvable_host_is_a_clean_error(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(http_adapter.socket, "getaddrinfo", boom)
    adapter = make(tmp_path, "http://agent.internal/x", extra=ALLOW)
    with pytest.raises(AdapterError, match="resolve"):
        adapter.run({})


def test_the_connection_is_pinned_to_the_validated_address(tmp_path, monkeypatch):
    """No second DNS lookup between the check and the connect (DNS rebinding)."""
    calls = []

    def getaddrinfo(host, port, *args, **kwargs):
        calls.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port))]

    connected = []

    def create_connection(address, *args, **kwargs):
        connected.append(address)
        raise ConnectionRefusedError("test")

    monkeypatch.setattr(http_adapter.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(http_adapter.socket, "create_connection", create_connection)
    adapter = make(tmp_path, "http://agent.internal/x", extra=ALLOW)
    with pytest.raises(AdapterError):
        adapter.run({})
    assert calls == ["agent.internal"] and connected == [("10.0.0.5", 80)]


# ---------------------------------------------------------------- TLS verification
def test_self_signed_certificates_are_rejected(tmp_path):
    import shutil
    import ssl
    import subprocess

    if shutil.which("openssl") is None:
        pytest.skip("openssl not available")
    key, crt = tmp_path / "k.pem", tmp_path / "c.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key),
         "-out", str(crt), "-days", "1", "-subj", "/CN=localhost",
         "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
        check=True, capture_output=True,
    )  # fmt: skip
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(crt), str(key))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    httpd.daemon_threads = True
    threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True).start()
    try:
        adapter = make(tmp_path, f"https://127.0.0.1:{httpd.server_address[1]}/ok", extra="timeout_seconds = 5")
        with pytest.raises(AdapterError, match="TLS"):
            adapter.run({})
    finally:
        httpd.shutdown()
        httpd.server_close()
