"""`tests.conftest.platform_skip_reason`: the OS-tier gate's decision, alone.

The gate itself lives in `pytest_collection_modifyitems` and cannot be
observed from this workspace's own CI: both runners in
`.github/workflows/verify.yml` are POSIX (`macos-latest`, `ubuntu-latest`),
so the branch that skips brig's OS-driven tiers is unreachable there. What
IS testable is the decision, and that is what this file tests -- by passing
`os.name` in as a value rather than reading the host's.

What this file therefore does NOT prove, and what nothing on a POSIX machine
can: that pytest actually skips those items during collection on a non-POSIX
host. Only a Windows runner shows that, and this workspace has none.
"""

from __future__ import annotations

import pytest

from tests.conftest import platform_skip_reason


@pytest.mark.unit
@pytest.mark.parametrize("tier", ["unit", "integration", "e2e"])
def test_posix_never_skips_any_tier(tier: str) -> None:
    assert platform_skip_reason("posix", frozenset({tier})) is None


@pytest.mark.unit
def test_a_non_posix_host_skips_the_integration_tier() -> None:
    reason = platform_skip_reason("nt", frozenset({"integration"}))
    assert reason is not None
    assert "integration" in reason
    assert "'nt'" in reason


@pytest.mark.unit
def test_a_non_posix_host_skips_the_e2e_tier() -> None:
    reason = platform_skip_reason("nt", frozenset({"e2e"}))
    assert reason is not None
    assert "e2e" in reason


@pytest.mark.unit
def test_a_non_posix_host_still_runs_the_unit_tier() -> None:
    """The unit tier drives no OS mechanism, so it is not gated on the OS --
    the skip is scoped to `_OS_TIERS`, not to the platform alone."""
    assert platform_skip_reason("nt", frozenset({"unit"})) is None


@pytest.mark.unit
def test_the_reason_names_the_tier_and_the_platform() -> None:
    """A skip has to be visible BY NAME (the workspace's e2e rule), so the
    reason string is part of the contract, not an incidental message."""
    assert platform_skip_reason("java", frozenset({"e2e"})) == (
        "brig's e2e tier drives real POSIX process mechanisms; os.name is 'java'"
    )
