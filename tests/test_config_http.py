"""[adapters.NAME] type = "http" entries: parsing only. No network is touched here."""
import json

import pytest

from agentproof.config import ConfigError, HttpAdapterConfig, load_config


def load(tmp_path, body: str):
    f = tmp_path / "agentproof.toml"
    f.write_text(body, encoding="utf-8")
    f.chmod(0o600)
    return load_config(f)


def entry(extra: str = "", url: str = "http://127.0.0.1:8000/agent") -> str:
    return f'[adapters.web]\ntype = "http"\nurl = {json.dumps(url)}\n{extra}\n'


def test_minimal_http_entry_and_defaults(tmp_path):
    cfg = load(tmp_path, entry()).adapters["web"]
    assert isinstance(cfg, HttpAdapterConfig)
    assert (cfg.scheme, cfg.host, cfg.port, cfg.path) == ("http", "127.0.0.1", 8000, "/agent")
    assert cfg.url == "http://127.0.0.1:8000/agent"
    assert cfg.timeout_seconds == 30 and cfg.max_response_bytes == 1_000_000
    assert cfg.allow_hosts == () and cfg.allow_insecure_http is False and cfg.headers_env == ()


@pytest.mark.parametrize(
    ("url", "scheme", "host", "port", "path"),
    [
        ("http://localhost/", "http", "localhost", 80, "/"),
        ("http://localhost", "http", "localhost", 80, "/"),
        ("http://[::1]:9000/x", "http", "::1", 9000, "/x"),
        ("HTTP://LocalHost:81/A/b", "http", "localhost", 81, "/A/b"),
    ],
)
def test_url_normalisation_for_loopback_hosts(tmp_path, url, scheme, host, port, path):
    cfg = load(tmp_path, entry(url=url)).adapters["web"]
    assert (cfg.scheme, cfg.host, cfg.port, cfg.path) == (scheme, host, port, path)


def test_https_with_allow_listed_host_and_headers(tmp_path):
    body = entry(
        'allow_hosts = ["api.example.com"]\ntimeout_seconds = 5\nmax_response_bytes = 2000\n'
        '[adapters.web.headers_env]\nAuthorization = "MY_TOKEN"\nX-Team = "TEAM_ID"\n',
        url="https://api.example.com/v1/run",
    )
    cfg = load(tmp_path, body).adapters["web"]
    assert cfg.port == 443 and cfg.allow_hosts == ("api.example.com",)
    assert dict(cfg.headers_env) == {"Authorization": "MY_TOKEN", "X-Team": "TEAM_ID"}
    assert cfg.timeout_seconds == 5 and cfg.max_response_bytes == 2000


def test_subprocess_entries_still_work_next_to_http_entries(tmp_path):
    body = entry() + '\n[adapters.cmd]\ntier = "A"\nargv = ["/usr/bin/python3"]\nacknowledge_not_sandboxed = true\n'
    cfgs = load(tmp_path, body).adapters
    assert set(cfgs) == {"web", "cmd"} and not isinstance(cfgs["cmd"], HttpAdapterConfig)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://127.0.0.1/",
        "file:///etc/passwd",
        "http://user:pw@127.0.0.1/",
        "http://127.0.0.1/?key=secret",
        "http://127.0.0.1/#frag",
        "http:///nohost",
        "http://127.0.0.1:0/",
        "http://127.0.0.1:70000/",
        "http://127.0.0.1/" + "a" * 2100,
        "http://exa mple.com/",
        "http://api.example.com/",  # not loopback and not in allow_hosts
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/",
        "",
    ],
)
def test_bad_urls_are_rejected_without_echoing_secrets(tmp_path, url):
    with pytest.raises(ConfigError) as exc:
        load(tmp_path, entry(url=url))
    text = str(exc.value)
    assert "pw" not in text.replace("password", "") and "secret" not in text


def test_url_must_be_a_string_and_present(tmp_path):
    with pytest.raises(ConfigError, match="url"):
        load(tmp_path, '[adapters.web]\ntype = "http"\n')
    with pytest.raises(ConfigError, match="url"):
        load(tmp_path, '[adapters.web]\ntype = "http"\nurl = 5\n')


def test_plain_http_to_a_non_loopback_host_needs_explicit_opt_in(tmp_path):
    body = 'allow_hosts = ["api.example.com"]\n'
    with pytest.raises(ConfigError, match="allow_insecure_http"):
        load(tmp_path, entry(body, url="http://api.example.com/"))
    cfg = load(tmp_path, entry(body + "allow_insecure_http = true\n", url="http://api.example.com/"))
    assert cfg.adapters["web"].allow_insecure_http is True


@pytest.mark.parametrize(
    "extra",
    [
        'allow_hosts = "api.example.com"',
        "allow_hosts = [1]",
        'allow_hosts = ["Api Example"]',
        'allow_hosts = ["a.com", "a.com"]',
        'allow_hosts = ["https://a.com"]',
        "allow_hosts = " + str([f"h{i}.example.com" for i in range(33)]),
        "allow_insecure_http = 1",
        "timeout_seconds = 0",
        "timeout_seconds = 301",
        'timeout_seconds = "5"',
        "timeout_seconds = true",
        "max_response_bytes = 0",
        "max_response_bytes = 1000001",
        "max_response_bytes = 1.5",
        'headers_env = "X"',
        'unknown_key = 1',
        'tier = "A"',
        "acknowledge_not_sandboxed = true",
        'argv = ["/usr/bin/python3"]',
    ],
)
def test_bad_options_are_rejected(tmp_path, extra):
    with pytest.raises(ConfigError):
        load(tmp_path, entry(extra))


@pytest.mark.parametrize(
    "header_line",
    [
        'Host = "X"',  # framing / routing headers may not be overridden
        '"Content-Length" = "X"',
        '"Content-Type" = "X"',
        '"Transfer-Encoding" = "X"',
        '"Bad Header" = "X"',
        '"X-A" = "bad name"',
        '"X-A" = "PATH"',  # env names that change code loading are refused everywhere
        '"X-A" = 5',
        '"X-A" = ""',
    ],
)
def test_bad_headers_env_entries_are_rejected(tmp_path, header_line):
    body = entry() + f"[adapters.web.headers_env]\n{header_line}\n"
    with pytest.raises(ConfigError):
        load(tmp_path, body)


def test_http_adapter_name_cannot_shadow_a_builtin_runner(tmp_path):
    with pytest.raises(ConfigError, match="shadow"):
        load(tmp_path, '[adapters.local]\ntype = "http"\nurl = "http://127.0.0.1/"\n')


def test_unknown_type_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="type"):
        load(tmp_path, '[adapters.web]\ntype = "grpc"\nurl = "http://127.0.0.1/"\n')
