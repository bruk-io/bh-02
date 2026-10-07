"""The credential file, the CLI child's environment, and the detached launcher's scrub; no process.

The token here is a stand-in written to a temporary file: no real credential is ever read."""

import traceback
from pathlib import Path

from models_cordis_plugin.claude_code import TOKEN_VARIABLE, ChildEnv, child_env, scrubbed
from models_cordis_plugin.local_env import parse_env, token_file

_FAKE = "sentinel-not-a-real-token"


def test_parse_env_reads_key_value_lines_and_skips_the_rest() -> None:
    text = "\n".join(
        [
            "# a comment",
            "",
            "PLAIN=one",
            "export EXPORTED=two",
            "QUOTED='three'",
            'DOUBLE="four"',
            "  SPACED = five  ",
            "no equals sign here",
            "EQUALS=a=b",
            "=nokey",
        ]
    )
    assert parse_env(text) == {
        "PLAIN": "one",
        "EXPORTED": "two",
        "QUOTED": "three",
        "DOUBLE": "four",
        "SPACED": "five",
        "EQUALS": "a=b",
    }


def test_child_env_carries_the_token_config_dir_and_fixed_settings(tmp_path: Path) -> None:
    env_file = tmp_path / "local.env"
    env_file.write_text(f"# bh-02\n{TOKEN_VARIABLE}={_FAKE}\nOTHER=x\n")
    env = child_env(env_file, "/state/config")
    assert env is not None
    assert env[TOKEN_VARIABLE] == _FAKE
    assert env["CLAUDE_CONFIG_DIR"] == "/state/config"
    assert env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "0" and env["DISABLE_AUTO_COMPACT"] == "1"
    # a failed stream is an error the step reads, never Claude Code's unseen non-streaming retry
    assert env["CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK"] == "1"
    assert "OTHER" not in env  # only the credential leaves the file
    assert not any(key.startswith("ANTHROPIC_") for key in env)


def test_child_env_is_none_without_a_file_or_a_token(tmp_path: Path) -> None:
    assert child_env(None, "/c") is None
    assert child_env(tmp_path / "missing.env", "/c") is None
    empty = tmp_path / "local.env"
    empty.write_text(f"{TOKEN_VARIABLE}=\n")
    assert child_env(empty, "/c") is None


def test_the_child_env_never_shows_a_value_in_its_repr_or_a_traceback(tmp_path: Path) -> None:
    """Textual prints a crash with every frame's locals, through repr: the env names keys only."""
    env_file = tmp_path / "local.env"
    env_file.write_text(f"{TOKEN_VARIABLE}={_FAKE}\n")
    env = child_env(env_file, "/c")
    assert isinstance(env, ChildEnv)
    assert _FAKE not in repr(env) and _FAKE not in str(env) and TOKEN_VARIABLE in repr(env)

    def crash(held: ChildEnv) -> None:
        raise RuntimeError("boom")

    try:
        crash(env)
    except RuntimeError as error:
        printed = traceback.TracebackException.from_exception(error, capture_locals=True)
    assert all(_FAKE not in repr(frame.locals) for frame in printed.stack[1:])


def test_the_credential_is_the_nearest_searched_file_and_never_a_directory(tmp_path: Path) -> None:
    """On Linux the jail holds an absent searched `local.env` with an empty directory while it
    runs: that must never hide the real file further up, at the first read or a later one (the
    row reads it again at each Claude Code start: after /model, /clear, a failed step)."""
    near, mid, root = (tmp_path / "a" / "b", tmp_path / "a", tmp_path)
    searched = [str(near / "local.env"), str(mid / "local.env"), str(root / "local.env")]
    assert token_file(None, searched) is None  # nothing there: no file
    (root / "local.env").write_text(f"{TOKEN_VARIABLE}={_FAKE}\n")
    (near / "local.env").mkdir(parents=True)  # a jail's placeholder, nearer
    assert token_file(None, searched) == root / "local.env"
    assert child_env(token_file(None, searched), "/c") is not None  # and it reads
    (mid / "local.env").mkdir()  # another, made while the session runs
    assert token_file(None, searched) == root / "local.env"  # read again: still the real one
    (mid / "local.env").rmdir()
    (mid / "local.env").write_text("OTHER=1\n")  # a real file, nearer: that one is the credential
    assert token_file(None, searched) == mid / "local.env"
    assert token_file(str(near / "local.env"), searched) == near / "local.env"  # env_file wins
    assert child_env(near / "local.env", "/c") is None  # a directory named there reads as no token


def test_the_detached_launcher_drops_every_variable_that_would_leave_the_subscription() -> None:
    kept = {
        TOKEN_VARIABLE: _FAKE,
        "CLAUDE_CONFIG_DIR": "/state/config",
        "CLAUDE_CODE_ENTRYPOINT": "sdk-py",
        "CLAUDE_AGENT_SDK_VERSION": "0.2.158",
        "ENABLE_CLAUDEAI_MCP_SERVERS": "0",
        "PATH": "/bin",
        "HTTPS_PROXY": "http://proxy:3128",
    }
    dropped = {
        "ANTHROPIC_BASE_URL": "x",
        "ANTHROPIC_MODEL": "y",
        "ANTHROPIC_ANYTHING": "z",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_CODE_USE_VERTEX": "1",
        "CLAUDE_CODE_USE_FOUNDRY": "1",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "100",
        "CLAUDE_CODE_SKIP_BEDROCK_AUTH": "1",
    }
    assert scrubbed(kept | dropped) == kept
