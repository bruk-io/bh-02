"""The one place a bh-02 `Policy` becomes the new brig's policies: its `FsPolicy` (what the
program may read and write, and what is kept from it), its `EnvPolicy` (the names of the
environment that reach it), the candidate environment those names are taken from, its `Stdio` and its
`EgressPolicy` (the destinations the person granted).
No other module's signature names a brig policy.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from brig import Claim, Destination, EgressPolicy, EnvPolicy, FsPolicy, Grade, Stdio

from runner_cordis_plugin.grants import NO_GRANTS, Grants, Kind
from runner_cordis_plugin.policy import Policy

__all__ = ["Brigged", "report_of", "to_brig"]


@dataclass(frozen=True, slots=True)
class Brigged:
    """What `create_bwrap_jail` is given for a `Policy`: `fs`, `env_policy`, `env` (the candidate
    environment, not yet scrubbed), `stdio` and `egress` (every start has one, empty until a
    destination is granted)."""

    fs: FsPolicy
    env_policy: EnvPolicy
    env: Mapping[str, str]
    stdio: Stdio
    egress: EgressPolicy


def to_brig(
    policy: Policy, *, grants: Grants = NO_GRANTS, environ: Mapping[str, str], stdout: str, stderr: str
) -> Brigged:
    """`policy` as brig takes it. `fs`: the readable roots, the writable roots, the write denies and
    the masks, as intent; brig compiles them and makes what a deny or mask at an absent path needs.
    `env_policy`: an allow-list of the policy's `env_allow` and the names it sets itself, and `env`:
    `environ` with those set (`TMPDIR`, the git author), so the allow-list is the one thing that
    decides what the program sees. `stdio`: the program's stdin is `/dev/null`, its stdout and
    stderr the files `stdout` and `stderr` name (outside every writable root, which brig refuses
    otherwise). `egress`: a `Destination` for each net grant in `grants` (the others are
    `spec_for`'s, which checked them against the floor; a net grant has no floor), and nothing else
    is reachable."""
    own = dict(policy.env_set)
    return Brigged(
        fs=FsPolicy(
            readable=policy.readable,
            writable=policy.writable,
            write_denies=policy.write_denies,
            masks=policy.masks,
        ),
        env_policy=EnvPolicy(allowed=tuple(dict.fromkeys((*policy.env_allow, *own)))),
        env=frozendict({**environ, **own}),
        stdio=Stdio(stdin="/dev/null", stdout=stdout, stderr=stderr),
        egress=EgressPolicy(allow=tuple(Destination(g.target, g.port) for g in grants.of(Kind.NET))),
    )


def report_of(report: Mapping[Claim, Grade]) -> dict[str, str]:
    """A jail's report as the runner's (CONTRACTS.md: report): each claim by its name, each grade
    in lower case (`best_effort`), exactly as brig graded them."""
    return {claim.name: grade.value.lower() for claim, grade in report.items()}
