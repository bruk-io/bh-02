"""A key an endpoint's `key_command` prints: for an openai endpoint whose key is not a line of
`local.env` but comes from a helper (a company's token tool, a password manager), the same way
Claude Code's `apiKeyHelper` gets one.

The command runs as the person, through their shell, with bh-02's environment and no input, when a
request needs a key; what it prints on stdout, trimmed, is the key. It is never held anywhere but
the request headers it goes into (the openai provider keeps those for `key_ttl_ms`, as Claude Code
keeps its helper's key), and an error about it names the command, never what it printed. Only the
models file may name one (`named`: never a layer's `extra`), as only it may name a factory.
"""

import asyncio
from typing import Final

from models_cordis_plugin.named import ModelsError

__all__ = ["DEFAULT_TTL_MS", "command_key"]

DEFAULT_TTL_MS: Final = (
    300_000  # how long a printed key is used when `key_ttl_ms` is unset (Claude Code's own)
)
_DEADLINE: Final = 60.0  # seconds: a first `npx` run downloads its package


async def command_key(name: str, command: str, *, deadline: float = _DEADLINE) -> str:
    """The key `command` prints for `name` (an endpoint or a model of one, as the person wrote it).

    Raises:
        ModelsError: the command can't be started, runs past `deadline`, fails, or prints nothing.
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as error:
        raise ModelsError(
            "authentication_failed", _failed(name, command, f"can't start ({error.strerror})")
        ) from None
    try:
        async with asyncio.timeout(deadline):
            printed, _ = await process.communicate()
    except TimeoutError:
        process.kill()
        await process.wait()
        raise ModelsError(
            "authentication_failed", _failed(name, command, f"printed no key within {deadline:g} s")
        ) from None
    if process.returncode != 0:
        raise ModelsError(
            "authentication_failed", _failed(name, command, f"exited with {process.returncode}")
        )
    if not printed.strip():
        raise ModelsError("authentication_failed", _failed(name, command, "printed nothing"))
    return printed.decode("utf-8", errors="replace").strip()


def _failed(name: str, command: str, what: str) -> str:
    """What the person is told when `name`'s key_command gives no key (`what` happened), never
    anything it printed."""
    return (
        f"{name!r}'s key_command `{command}` {what}, so the request has no key. Run it in a terminal to "
        "see why, fix it or its key_command in the models file, then send the message again."
    )
