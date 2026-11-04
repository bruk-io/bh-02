"""The words of the grants prompt: each kind says what, who and why, when and the grade effect, and a
path at a place where hosts keep sockets warns that network would be violated."""

from runner_cordis_plugin.grants import Asker, Grant, Kind, Request, Source
from runner_cordis_plugin.policy import SOCKET_PLACES
from runner_cordis_plugin.prompting import applies, question

_ASKER = Asker(Source.ROW, "python")


def _ask(grant: Grant, *, runtime_dir: str = "/run/user/1000", asker: Asker = _ASKER) -> dict[str, object]:
    request = Request(grant, asker, "it reads the dataset")
    return question(request, places=SOCKET_PLACES, runtime_dir=runtime_dir)


def test_a_path_grant_says_what_who_why_when_and_that_no_grade_changes() -> None:
    asked = _ask(Grant(Kind.READ, "/data/set"))
    lines = asked["lines"]
    assert isinstance(lines, list)
    assert lines[0] == "What: read /data/set"
    assert lines[1] == "Asked by: row python, because: it reads the dataset"
    assert lines[2] == f"When: {applies(Grant(Kind.READ, '/data/set'))}"
    assert "no grade changes" in lines[3]
    assert asked["warning"] == ""
    assert asked["title"] == "Allow read /data/set?"


def test_the_choices_are_once_always_no_and_escape_answers_no() -> None:
    asked = _ask(Grant(Kind.ENV, "EDITOR"))
    assert asked["choices"] == [
        {"key": "o", "value": "once", "label": "once (for this session)"},
        {"key": "a", "value": "always", "label": "always (for this project)"},
        {"key": "n", "value": "no", "label": "no"},
    ]
    assert asked["escape"] == "no"


def test_an_env_grant_says_the_value_reaches_the_program() -> None:
    lines = _ask(Grant(Kind.ENV, "EDITOR"))["lines"]
    assert isinstance(lines, list)
    assert lines[0] == "What: env EDITOR"
    assert "value reaches the program" in lines[3]


def test_a_net_grant_names_host_and_port_and_keeps_the_network_proxied() -> None:
    asked = _ask(Grant(Kind.NET, "example.com", 443))
    lines = asked["lines"]
    assert isinstance(lines, list)
    assert lines[0] == "What: net example.com:443"
    assert "next start" in lines[2]
    assert "proxied" in lines[3]
    assert asked["warning"] == ""


def test_a_path_that_is_under_holds_or_is_a_socket_place_warns_network_would_be_violated() -> None:
    for kind, target, meets in [
        (Kind.READ, "/run/user/1000/bus", "is under /run"),
        (Kind.READ, "/tmp", "is /tmp"),
        (Kind.READ, "/var", "holds /var/run"),
        (Kind.READ, "/run/user/1000/x", "is under /run/user/1000"),
        (Kind.WRITE, "/var", "holds /var/run"),  # a root that only holds one starts, and is violated
    ]:
        question = _ask(Grant(kind, target))
        warning = question["warning"]
        assert isinstance(warning, str)
        assert meets in warning, (kind, target, warning)
        assert "network would be violated" in warning.replace("'s network", " network")
        assert "stop counting it as confined" in warning


def test_a_write_at_or_under_a_socket_place_says_the_program_would_not_start() -> None:
    # Every start refuses a writable root there (`socket_refusal`): the jail is never graded.
    for target, meets in [
        ("/tmp", "is /tmp"),
        ("/tmp/work", "is under /tmp"),
        ("/run/user/1000/x", "is under /run/user/1000"),
    ]:
        question = _ask(Grant(Kind.WRITE, target))
        warning, lines = question["warning"], question["lines"]
        assert isinstance(warning, str) and isinstance(lines, list)
        assert meets in warning and "would not start while this grant stands" in warning, warning
        assert "/grants revoke" in warning and "violated" not in warning
        assert lines[3] == "Grades: none: the program would not start while this grant stands"


def test_the_runtime_directory_is_a_socket_place_only_when_set() -> None:
    assert _ask(Grant(Kind.READ, "/mnt/run/x"), runtime_dir="")["warning"] == ""
    assert "/mnt/run" in str(_ask(Grant(Kind.READ, "/mnt/run/x"), runtime_dir="/mnt/run")["warning"])


def test_a_write_on_a_self_modifying_path_warns_it_can_run_code_later() -> None:
    for target in ("/work/p/.git/hooks", "/work/p/.git/hooks/pre-commit", "/work/p/.envrc"):
        warning = _ask(Grant(Kind.WRITE, target))["warning"]
        assert isinstance(warning, str)
        assert "can run code outside the jail later" in warning
    assert _ask(Grant(Kind.READ, "/work/p/.envrc"))["warning"] == ""
    assert _ask(Grant(Kind.WRITE, "/work/p/src/env"))["warning"] == ""


def test_an_agent_that_asks_is_named() -> None:
    lines = _ask(Grant(Kind.NET, "example.com", 443), asker=Asker(Source.AGENT, "scout"))["lines"]
    assert isinstance(lines, list)
    assert lines[1].startswith("Asked by: agent scout")
