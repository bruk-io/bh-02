"""The one place a bh-02 `Policy` becomes the new brig's policies: its `FsPolicy` (what the
program may read and write, and what is kept from it), its `EnvPolicy` (the names of the
environment that reach it), the candidate environment those names are taken from, and its `Stdio`.
No other module's signature names a brig policy.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from brig import Claim, EnvPolicy, FsPolicy, Grade, Stdio

from runner_cordis_plugin.policy import Policy, ReadModel

__all__ = ["Brigged", "report_of", "to_brig"]

#: By denylist the program reads everything but its masks: the whole host, read-only, less them.
_WHOLE_HOST = ("/",)


@dataclass(frozen=True, slots=True)
class Brigged:
    """What `create_bwrap_jail` is given for a `Policy`: `fs`, `env_policy`, `env` (the candidate
    environment, not yet scrubbed) and `stdio`."""

    fs: FsPolicy
    env_policy: EnvPolicy
    env: Mapping[str, str]
    stdio: Stdio


def to_brig(policy: Policy, *, environ: Mapping[str, str], stdout: str, stderr: str) -> Brigged:
    """`policy` as brig takes it. `fs`: the readable roots (the policy's, or the whole host by
    denylist), the writable roots, the write denies and the masks, as intent; brig compiles them
    and makes what a deny or mask at an absent path needs. `env_policy`: an allow-list of the
    policy's `env_allow` and the names it sets itself, and `env`: `environ` with those set
    (`TMPDIR`, the git author), so the allow-list is the one thing that decides what the program
    sees. `stdio`: the program's stdin is `/dev/null`, its stdout and stderr the files `stdout` and
    `stderr` name (outside every writable root, which brig refuses otherwise)."""
    readable = _WHOLE_HOST if policy.read_model is ReadModel.DENYLIST else policy.readable
    own = dict(policy.env_set)
    return Brigged(
        fs=FsPolicy(
            readable=readable,
            writable=policy.writable,
            write_denies=policy.write_denies,
            masks=policy.masks,
        ),
        env_policy=EnvPolicy(allowed=tuple(dict.fromkeys((*policy.env_allow, *own)))),
        env=frozendict({**environ, **own}),
        stdio=Stdio(stdin="/dev/null", stdout=stdout, stderr=stderr),
    )


def report_of(report: Mapping[Claim, Grade]) -> dict[str, str]:
    """A jail's report as the runner's (CONTRACTS.md: report): each claim by its name, each grade
    in lower case (`best_effort`), exactly as brig graded them."""
    return {claim.name: grade.value.lower() for claim, grade in report.items()}
