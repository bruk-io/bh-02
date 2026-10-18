"""Paths as bh-02's own process must judge them when the model can write some of them: where the
person's directories are (`config_home`, `state_home`), every place reading a path goes through
(`walked`), held against the roots the model may write (`roots`, `passes`), and a file beneath a
root opened through no link (`directory_beneath`, `read_beneath`), and written or removed there
(`write_beneath`, `remove_beneath`), or appended to off the event loop (`Appender`, which
refuses a file replaced under it: `Replaced`)."""

from host_paths.appender import Appender, Replaced
from host_paths.beneath import (
    Link,
    Linked,
    NotOneFile,
    TooLarge,
    directory_beneath,
    read_beneath,
    remove_beneath,
    write_beneath,
)
from host_paths.paths import MOST_LINKS, config_home, passes, roots, state_home, walked

__all__ = [
    "MOST_LINKS",
    "Appender",
    "Link",
    "Linked",
    "NotOneFile",
    "Replaced",
    "TooLarge",
    "config_home",
    "directory_beneath",
    "passes",
    "read_beneath",
    "remove_beneath",
    "roots",
    "state_home",
    "walked",
    "write_beneath",
]
