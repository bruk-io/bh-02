"""The CLI child's environment and the detached launcher's scrub; no process.

The token here is a stand-in: no real credential is ever read."""

import traceback

from models_cordis_plugin.claude_code import (
    API_KEY_VARIABLE,
    TOKEN_VARIABLE,
    ChildEnv,
    child_env,
    gateway_env,
    scrubbed,
)

_FAKE = "sentinel-not-a-real-token"


def test_child_env_carries_the_token_config_dir_and_fixed_settings() -> None:
    env = child_env(_FAKE, "/state/config")
    assert env[TOKEN_VARIABLE] == _FAKE
    assert env["CLAUDE_CONFIG_DIR"] == "/state/config"
    assert env["ENABLE_CLAUDEAI_MCP_SERVERS"] == "0" and env["DISABLE_AUTO_COMPACT"] == "1"
    # a failed stream is an error the step reads, never Claude Code's unseen non-streaming retry
    assert env["CLAUDE_CODE_DISABLE_NONSTREAMING_FALLBACK"] == "1"
    assert env[API_KEY_VARIABLE] == ""  # the one not chosen is empty, never absent
    assert {key for key in env if key.startswith("ANTHROPIC_")} == {API_KEY_VARIABLE}


def test_the_child_env_never_shows_a_value_in_its_repr_or_a_traceback() -> None:
    """Textual prints a crash with every frame's locals, through repr: the env names keys only."""
    env = child_env(_FAKE, "/c")
    assert isinstance(env, ChildEnv)
    assert _FAKE not in repr(env) and _FAKE not in str(env) and TOKEN_VARIABLE in repr(env)

    def crash(held: ChildEnv) -> None:
        raise RuntimeError("boom")

    try:
        crash(env)
    except RuntimeError as error:
        printed = traceback.TracebackException.from_exception(error, capture_locals=True)
    assert all(_FAKE not in repr(frame.locals) for frame in printed.stack[1:])


def test_the_detached_launcher_drops_every_variable_that_would_change_the_steps() -> None:
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


def test_an_api_key_goes_in_its_own_variable_and_the_token_s_is_empty() -> None:
    env = child_env(_FAKE, "/state/config", api_key=True)
    assert env[API_KEY_VARIABLE] == _FAKE and env[TOKEN_VARIABLE] == ""
    assert _FAKE not in repr(env)


def test_a_gateway_s_environment_has_neither_credential() -> None:
    env = gateway_env("/state/config")
    assert env[API_KEY_VARIABLE] == "" and env[TOKEN_VARIABLE] == ""


def test_what_a_shell_exported_never_reaches_the_cli_whichever_way_it_authenticates() -> None:
    """The SDK merges bh-02's environment under the child's, and the detached launcher keeps both
    credential variables: so each start sets both, and a shell's own value of either is overridden."""
    shell = {API_KEY_VARIABLE: "from-the-shell", TOKEN_VARIABLE: "also-from-the-shell", "PATH": "/bin"}
    for env in (child_env(_FAKE, "/c"), child_env(_FAKE, "/c", api_key=True), gateway_env("/c")):
        reaching = scrubbed({**shell, **env})
        assert "from-the-shell" not in reaching.values() and "also-from-the-shell" not in reaching.values()
        assert reaching["PATH"] == "/bin"
    assert scrubbed({**shell, **child_env(_FAKE, "/c", api_key=True)})[API_KEY_VARIABLE] == _FAKE
