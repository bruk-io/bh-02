# host-paths

Paths as bh-02's own process must judge them when the model can write some of them. `README.md`
says what each name is; this file is where things go and what the gate holds.

## Layout

- `src/host_paths/paths.py`: `config_home`, `state_home`, `walked`, `MOST_LINKS`, `roots` and
  `passes`.
- `src/host_paths/beneath.py`: the opener of a file beneath a root through no link,
  `directory_beneath` and `read_beneath`, and what they raise (`Linked`, `NotOneFile`,
  `TooLarge`) or answer for a final link (`Link`); and the writer and remover of one,
  `write_beneath` and `remove_beneath`, which refuse a link or a second name (`Linked`,
  `NotOneFile`) and never follow it. Its docstring says why each flag. `__init__.py` only
  re-exports.
- `src/host_paths/appender.py`: `Appender`, the one appender of a file bh-02 keeps for the person (a
  transcript, a sub-agent's event log, a session's row log): a queue of writes on one thread, opened
  for append through no link at 0600, `flush` and `close` waiting for the last, a failed write kept
  and raised, a file replaced under it refused (`Replaced`). Its docstring says why each flag.
- `tests/test_host_paths.py`: the XDG directories (an empty or relative value is unset), the walk
  against a table of links in a temporary directory (absolute, relative, the file itself, `..`
  after a link, dangling, missing, a loop that ends at `MOST_LINKS`), and `passes` over roots as
  named and as resolved.
- `tests/test_host_paths_beneath.py`: the opener against a table of what the model could leave
  beneath a root: a link at each depth, a final link (and a dangling one), a hard link, a pipe, a
  directory, a file on the way, a file over the cap, a file gone between the walk and the read,
  and names that are not one step.
- `tests/test_host_paths_appender.py`: the appender: bytes in the order queued, `append` with no event
  loop, a held write that `append` returns before and `flush` waits for, a cancelled waiter, a link
  refused (at once and at the first write), the mode under a umask that takes nothing away, `new`, a
  failed write (raised by `append`, `flush` and `close`, nothing after it written), a file replaced
  under it (renamed over, removed, turned into a link: held or not yet opened, `Replaced`, nothing
  written to either file) and `close`.
- `tests/test_host_paths_writing.py`: the writer and the remover against the same table, with a
  link to a file outside the root, a dangling one and a hard link among the cases: nothing outside
  the root is written or removed, and a link planted after the check is replaced, not followed.

## What belongs here

A function every package that decides whether to trust a file by where it is, and how it is
reached, must compute alike: the models plugin (the models file), the python plugin (the person's
startup file), memory (memory files outside the project, and in it through no link; the auto
memory directory, written through no link), the app
and brig (the XDG directories), agent (the project's `.git/HEAD`) and the extensions host (the
model's extensions). The appender is the same kind of function for the files bh-02 writes as a
session goes on (the agent plugin's transcript, the sub-agents' event log, the shell's row log):
written off the event loop, at 0600, through no link. bh-02's plugins may import nothing of each other's, so a copy in
each would drift, and a drifted copy is a hole. It depends on the standard library alone: no
cordis, no key, row or bh-02 path. A function that names any of those stays in its plugin.

## The gate

`pyproject.toml` here keeps its own `[tool.pypeeker]` gate, run by `scripts/arch-check` with the
rest. Everything under `host_paths.*` is pure except the names in
`[tool.pypeeker.no-impure-functions].exclude`: `walked`, `roots` and `passes` read links and
resolve paths, and the opener, writer and remover open, read, write and remove files, which is
what they are for.
