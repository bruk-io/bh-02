"""The `warden` command: boots the composition and supervises until Ctrl-C (or, under
`--tray`, until the menu-bar app quits).
"""

import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

import click

from warden.bootstrap import CompositionError, layers, run, run_with_tray

__all__ = ["main"]

_PATCH_HELP = "A layer file applied over the shipped composition. Repeatable."
_PATCH_TYPE = click.Path(exists=True, dir_okay=False, path_type=Path)


@click.command()
@click.option("--patch", "patches", multiple=True, type=_PATCH_TYPE, help=_PATCH_HELP)
@click.option("--trace", is_flag=True, help="Print every row's lifecycle event to stderr.")
@click.option("--tray", is_flag=True, help="A macOS menu-bar app instead of running until Ctrl-C.")
def main(patches: Sequence[Path], trace: bool, tray: bool) -> None:
    """Supervise the configured processes until Ctrl-C, or until the tray quits (--tray)."""
    listen = (lambda line: click.echo(f"  {line}", err=True)) if trace else None

    def report(line: str) -> None:
        click.echo(f"error: {line}", err=True)

    try:
        if tray:
            run_with_tray([*layers(tray=True), *patches], trace=listen, report=report)
        else:
            asyncio.run(run([*layers(), *patches], trace=listen, report=report))
    except CompositionError as error:
        click.echo(f"error: {error.message}", err=True)
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo()
