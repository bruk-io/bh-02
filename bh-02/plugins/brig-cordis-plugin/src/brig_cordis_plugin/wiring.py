"""The row: a brig jail, bound under `jail`."""

from brig_cordis_plugin.jail import BrigConfig, BrigJail, Layers
from cordis import Effects, bind, component

__all__ = ["jail"]


@component(provides=("jail",))
async def jail(*, config: BrigConfig, layers: Layers) -> Effects:
    """Fills a `jail` row: `use = "brig:jail"`. Depends on `layers` so a cell can never write
    the files the running composition is read from."""
    yield bind("jail", BrigJail(config, layers))
