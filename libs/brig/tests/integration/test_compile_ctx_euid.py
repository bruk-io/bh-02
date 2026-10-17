"""`build_compile_ctx` observes who is creating the jail, and the render follows it (decision-194).

The unit tier pins the render for each `euid`; this holds the one fact `mech` may not go and get:
`run`'s helper reads it from the process, so an embedder that builds its context the supported way
gets the cover of decision-177 as root and none as anyone else, with no argument to forget.
"""

from __future__ import annotations

import os

import pytest

from brig.core import FsPolicy, ReadModel, Spec
from brig.mech.bwrap import Bwrap
from brig.run.compile_ctx import build_compile_ctx

pytestmark = pytest.mark.integration


def test_the_context_carries_the_effective_user_and_the_cover_follows_it(
    tmp_path: pytest.TempPathFactory,
) -> None:
    spec = Spec(
        fs=FsPolicy(
            read_model=ReadModel.ALLOW_LIST,
            read_allows=("/usr",),
            write_allows=(str(tmp_path),),
        )
    )
    ctx = build_compile_ctx(spec, jail_dir=str(tmp_path / "jail"), platform="linux")
    assert ctx.euid == os.geteuid()

    argv = Bwrap(interpreter="/usr/bin/python3").compile(spec, ctx).wrap(("w",))
    covered = ("--ro-bind", "/proc/sys", "/proc/sys")
    has_cover = any(argv[i : i + 3] == covered for i in range(len(argv)))
    assert has_cover is (os.geteuid() == 0)
