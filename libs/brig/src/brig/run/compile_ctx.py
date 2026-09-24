"""`build_compile_ctx`: the one helper that resolves a `Spec` into a real
`CompileCtx` -- `run` being the layer permitted I/O where `mech` is not
(SPEC.md §6: "`mech` performs no I/O of its own during compile").

Owns TWO resolutions and, since decision-159 (2026-09-08), one further
OBSERVATION -- `path_exists` -- for the same reason: it is a fact about the
filesystem, `mech` may not go and get one, and `run` is the layer that may.

1. `resolved_paths` -- every `Spec` path a mechanism's render might need
   resolved (`fs.write_allows`, `fs.write_denies`, `fs.read_denies`,
   `fs.read_allows`, and every channel's `endpoint`), mapped to its
   `os.path.realpath` form, keyed EXACTLY as the `Spec` carries the path
   (never the resolved form as the key -- a mechanism's render looks up by
   the raw `Spec` value it already has in hand). `seatbelt` (task-058/
   task-059) is the first consumer and the reason this exists: a darwin
   `/tmp/...` path is a symlink to `/private/tmp/...`, and an SBPL rule
   written against the symlinked form silently matches nothing.
2. `jail_dir` itself -- NOT a `Spec` path, so `resolved_paths` cannot cover
   it, yet it is exactly the same trap: a jail directory handed as
   `/tmp/bgNNN` on darwin is the symlinked form. `CompileCtx`'s own
   docstring states the invariant ("the caller supplies a realpath'd
   jail_dir"); THIS function is that caller. Every mechanism's own render
   then only needs to hold a LEXICAL guard against the trap shape (see
   `brig.mech.seatbelt.profile`'s `UnresolvedPath` guard), never a realpath
   comparison -- that would be I/O a pure render may not perform.

Resolving the union of every Spec path field (not only the subset one
mechanism happens to need today) is deliberate: this helper is generic
`run`-layer plumbing, not seatbelt-specific, and an unused `resolved_paths`
entry costs nothing (it is a plain mapping a mechanism looks up into by
key; extra keys are inert).

**`path_exists` (decision-159).** For every path above, whether it exists.
`bwrap` is the first consumer and the reason this exists: a `write_denies`
carve-out is a bind mount over an existing path and an empty read-only
tmpfs over an absent one, and neither primitive covers the other's case --
so a mechanism that guessed would either fail the launch or leave the
carve-out silently not holding. `os.path.exists` follows symlinks, matching
`os.path.realpath` above: a dangling symlink is reported absent, which is
what both mount primitives will make of it too.

The window between this observation and the launch is real and is a
REFUSAL on both sides rather than a hole -- a path that appears in it makes
bwrap's `--tmpfs` fail, one that vanishes makes its `--ro-bind` fail, and a
mount that fails is a jail that does not start. Named here, where a reader
of the helper sees it, as well as in the mechanism that consumes it.

`os.path.realpath` never requires its target to exist: it resolves
symlinks in whatever existing path PREFIX it finds and appends the rest of
the path unchanged, so this works whether or not `jail_dir` (or a
not-yet-created path inside it, e.g. a LISTEN channel's own socket file)
has actually been created on disk yet.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from brig.core import Spec
from brig.mech import CompileCtx


def _spec_paths(spec: Spec) -> Iterator[str]:
    """Every path field a `Spec` carries that a mechanism's render might
    need resolved. A superset of what any single mechanism strictly needs
    (see this module's own docstring for why that is deliberate, not
    sloppy)."""
    yield from spec.fs.write_allows
    yield from spec.fs.write_denies
    yield from spec.fs.read_denies
    yield from spec.fs.read_allows
    for channel in spec.channels:
        yield channel.endpoint


def build_compile_ctx(spec: Spec, *, jail_dir: str, platform: str) -> CompileCtx:
    """Build a `CompileCtx` for `spec`, performing both resolutions and the
    one existence observation this module's own docstring names:
    `resolved_paths` (every `Spec` path above, mapped to its realpath'd
    form), `jail_dir` itself (realpath'd before construction -- it is not a
    `Spec` path, so `resolved_paths` cannot cover it, and `CompileCtx`'s own
    docstring states the caller must supply it already resolved), and
    `path_exists` (every `Spec` path above, mapped to whether it exists).

    This is the ONLY place in `run` that performs this resolution --
    `Mechanism.compile()` never calls `os.path.realpath` itself (SPEC.md
    §6: no I/O during compile), and a mechanism that needs a path this
    function did not resolve refuses (e.g. seatbelt's `UnresolvedPath`),
    naming it, rather than falling back to the unresolved form.
    """
    spec_paths = tuple(_spec_paths(spec))
    resolved_paths = {path: os.path.realpath(path) for path in spec_paths}
    path_exists = {path: os.path.exists(path) for path in spec_paths}
    return CompileCtx(
        jail_dir=os.path.realpath(jail_dir),
        platform=platform,
        resolved_paths=resolved_paths,
        path_exists=path_exists,
    )


__all__ = ("build_compile_ctx",)
