"""Grant values (decision-0012 items 1, 2, 5): the four kinds and what each takes, who asked and
why, and the floor no answer grants. All pure; the values are stand-ins."""

import pytest

from runner_cordis_plugin.grants import Answer, Asker, Floor, Grant, Invalid, Kind, Request, Source, refusal

FLOOR = Floor(
    secrets=("/state/sessions",),
    grants="/state/bh-02/projects/-w/grants",
    credentials=("/home/me/.ssh", "/home/me/.claude.json"),
    layers=("/w/app/mine.toml",),
    code=("/w/app/src/bh_02",),
    trusted=("/home/me/.config/bh-02",),
    interpreters=("/opt/py/bin/python3.15",),
    links=("/home/me/.local/share/uv/python",),
    key_envs={"WORK_KEY": ("work",), "OTHER": ("a", "b")},
)


def test_a_path_grant_takes_an_absolute_normal_path() -> None:
    for kind in (Kind.READ, Kind.WRITE):
        assert Grant(kind, "/data/in").target == "/data/in"
        for bad in ("data", "", "/a/../b", "/a/", "/a//b", "/./a", "//a", "/a\0b"):
            with pytest.raises(Invalid, match="absolute path|normal|NUL"):
                Grant(kind, bad)
        with pytest.raises(Invalid, match="whole filesystem"):
            Grant(kind, "/")
        with pytest.raises(Invalid, match="no port"):
            Grant(kind, "/a", 80)


def test_the_message_for_a_path_that_is_not_normal_says_what_to_write() -> None:
    with pytest.raises(Invalid, match=r"write '/a/b'"):
        Grant(Kind.READ, "/a/./b/")


def test_an_env_grant_takes_a_variable_name_and_never_a_value() -> None:
    assert Grant(Kind.ENV, "AWS_PROFILE").target == "AWS_PROFILE"
    for bad in ("", "1A", "A=b", "A B", "A-B"):
        with pytest.raises(Invalid, match="variable name.*never the value"):
            Grant(Kind.ENV, bad)
    with pytest.raises(Invalid, match="no port"):
        Grant(Kind.ENV, "A", 1)


def test_a_net_grant_is_a_name_a_wildcard_suffix_or_an_address_with_a_port() -> None:
    assert Grant(Kind.NET, "Example.COM", 443).target == "example.com"
    assert Grant(Kind.NET, "*.Example.com", 443).target == "*.example.com"
    assert Grant(Kind.NET, "10.0.0.1", 80).target == "10.0.0.1"
    assert Grant(Kind.NET, "::1", 80).target == "::1"
    assert Grant(Kind.NET, "::ffff:10.0.0.1", 80).target == "10.0.0.1"
    assert Grant(Kind.NET, "example.com.", 80).target == "example.com"
    assert Grant(Kind.NET, "xn--bcher-kva.example", 80).kind is Kind.NET


@pytest.mark.parametrize(
    ("host", "port", "message"),
    [
        ("example.com", 0, "port from 1 to 65535"),
        ("example.com", 65536, "port from 1 to 65535"),
        ("example.com", -1, "port from 1 to 65535"),
        ("", 80, "takes a host"),
        ("[::1]", 80, "without brackets"),
        ("10.0.0.0/8", 80, "not a range"),
        ("*", 80, "first label"),
        ("*example.com", 80, "first label"),
        ("a.*.example.com", 80, "first label"),
        ("*.*.example.com", 80, "first label"),
        ("*.10.0.0.1", 80, "not an address"),
        ("-bad.example", 80, "neither a hostname"),
        ("a_b.example", 80, "neither a hostname"),
        ("bücher.example", 80, "xn--"),
        ("fe80::1%eth0", 80, "no zone"),
        ("10.1", 80, "neither a hostname"),
        ("0x7f", 80, "neither a hostname"),
        ("a" * 64 + ".com", 80, "neither a hostname"),
    ],
)
def test_a_net_grant_that_brig_would_refuse_is_refused_with_what_to_write(
    host: str, port: int, message: str
) -> None:
    with pytest.raises(Invalid, match=message):
        Grant(Kind.NET, host, port)


def test_a_request_needs_a_reason_and_a_name() -> None:
    grant = Grant(Kind.READ, "/data")
    request = Request(grant, Asker(Source.EXTENSION, "lint"), "reads the data")
    assert str(request.asker) == "extension lint"
    with pytest.raises(Invalid, match="no reason"):
        Request(grant, Asker(Source.ROW, "python"), "  ")
    with pytest.raises(Invalid, match="name the row, tool, extension or agent"):
        Request(grant, Asker(Source.AGENT, ""), "why")


def test_the_answers_are_once_always_and_no() -> None:
    assert [a.value for a in Answer] == ["once", "always", "no"]
    assert {s.value for s in Source} == {"row", "input", "extension", "agent"}


@pytest.mark.parametrize(
    ("kind", "path", "why"),
    [
        (Kind.READ, "/state/sessions", "secret"),
        (Kind.READ, "/state/sessions/abc/token", "secret"),
        (Kind.WRITE, "/state/sessions", "secret"),
        (Kind.READ, "/state/bh-02/projects/-w/grants", "grants store"),
        (Kind.READ, "/state/bh-02/projects/-w/grants/grants.toml", "grants store"),
        (Kind.WRITE, "/state/bh-02/projects/-w/grants/grants.toml", "could grant anything"),
        (Kind.READ, "/home/me/.ssh", "credentials"),
        (Kind.WRITE, "/home/me/.ssh/id", "credentials"),
        (Kind.READ, "/home/me/.claude.json", "credentials"),
        (Kind.WRITE, "/w/app/mine.toml", "layer file"),
        (Kind.WRITE, "/w/app/src/bh_02/x.py", "own code"),
        (Kind.WRITE, "/home/me/.config/bh-02/models.toml", "configuration"),
        (Kind.WRITE, "/opt/py/bin/python3.15", "interpreter"),
        (Kind.WRITE, "/home/me/.local/share/uv/python", "link"),
    ],
)
def test_what_the_host_keeps_is_never_granted_and_the_refusal_says_why(
    kind: Kind, path: str, why: str
) -> None:
    said = refusal(Grant(kind, path), FLOOR)
    assert said is not None and why in said and "never granted" in said and "Nothing can approve it" in said


def test_the_floor_is_by_kind_reading_what_the_host_runs_is_not_the_danger() -> None:
    for path in ("/w/app/mine.toml", "/w/app/src/bh_02/x.py", "/opt/py/bin/python3.15"):
        assert refusal(Grant(Kind.READ, path), FLOOR) is None
    # only the link's directory itself, not what lies beside it
    assert refusal(Grant(Kind.WRITE, "/home/me/.local/share/uv/python/other"), FLOOR) is None
    assert (
        refusal(Grant(Kind.WRITE, "/home/me/.local/share/uv"), FLOOR) is None
    )  # spec_for denies the link inside


def test_a_path_beside_the_floor_is_granted() -> None:
    for path in ("/state/sessions2", "/state/bh-02/projects/-w/grants-other", "/home/me/.sshx", "/data"):
        assert refusal(Grant(Kind.WRITE, path), FLOOR) is None
        assert refusal(Grant(Kind.READ, path), FLOOR) is None


def test_a_variable_a_model_key_reads_is_never_granted_and_names_the_endpoints() -> None:
    said = refusal(Grant(Kind.ENV, "OTHER"), FLOOR)
    assert said is not None and "'a', 'b'" in said and "model key" in said
    assert refusal(Grant(Kind.ENV, "WORK_KEY"), FLOOR) is not None
    assert refusal(Grant(Kind.ENV, "WORK_KEY"), Floor()) is None
    assert refusal(Grant(Kind.ENV, "AWS_PROFILE"), FLOOR) is None


@pytest.mark.parametrize("name", ["HTTP_PROXY", "https_proxy", "ALL_PROXY", "no_proxy", "Http_Proxy"])
def test_the_proxy_variables_are_never_granted_in_either_case(name: str) -> None:
    said = refusal(Grant(Kind.ENV, name), Floor())
    assert said is not None and "proxy" in said and "`net`" in said


def test_a_net_grant_is_not_on_the_floor() -> None:
    assert refusal(Grant(Kind.NET, "example.com", 443), FLOOR) is None
