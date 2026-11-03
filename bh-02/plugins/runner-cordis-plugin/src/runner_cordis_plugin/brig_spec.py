"""The one place a bh-02 `Policy` becomes the old brig's `Spec` (with its `FsPolicy`, `EnvPolicy`,
`ReadModel` and `Channel`). The swap to the new brig replaces this function and the shell
(`jail`); no other module's signature names brig's Spec.
"""

from brig.core import Channel, ChannelKind, EnvMode, EnvPolicy, FsPolicy, Spec
from brig.core import ReadModel as BrigReadModel
from runner_cordis_plugin.policy import Policy, ReadModel

__all__ = ["to_brig_spec"]

_READ_MODELS = {ReadModel.DENYLIST: BrigReadModel.DENY_LIST, ReadModel.ALLOWLIST: BrigReadModel.ALLOW_LIST}


def to_brig_spec(policy: Policy) -> Spec:
    """`policy` as the old brig's Spec: the writable roots and denies, the read model with its
    readable roots, the masks as read denies (brig's carve-outs under the allowlist), the scrubbed
    environment, and the one channel the program listens on."""
    return Spec(
        fs=FsPolicy(
            write_allows=policy.writable,
            write_denies=policy.write_denies,
            read_model=_READ_MODELS[policy.read_model],
            read_allows=policy.readable,
            read_denies=policy.masks,
        ),
        env=EnvPolicy(mode=EnvMode.SCRUB, allow_names=policy.env_allow, set=policy.env_set),
        channels=(Channel(name=policy.channel, kind=ChannelKind.LISTEN),),
    )
