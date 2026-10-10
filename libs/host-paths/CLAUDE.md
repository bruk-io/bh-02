# host-paths

Paths as bh-02's own process must judge them when the model can write some of them. `README.md`
says what each name is; this file is where things go and what the gate holds.

## Layout

- `src/host_paths/paths.py`: `config_home`, `state_home`, `walked`, `MOST_LINKS`, `roots` and
  `passes`.
- `src/host_paths/beneath.py`: the opener of a file beneath a root through no link,
  `directory_beneath` and `read_beneath`, and what they raise (`Linked`, `NotOneFile`,
  `TooLarge`) or answer for a final link (`Link`). Its docstring says why each flag. `__init__.py`
  only re-exports.
- `tests/test_host_paths.py`: the XDG directories (an empty or relative value is unset), the walk
  against a table of links in a temporary directory (absolute, relative, the file itself, `..`
  after a link, dangling, missing, a loop that ends at `MOST_LINKS`), and `passes` over roots as
  named and as resolved.
- `tests/test_host_paths_beneath.py`: the opener against a table of what the model could leave
  beneath a root: a link at each depth, a final link (and a dangling one), a hard link, a pipe, a
  directory, a file on the way, a file over the cap, a file gone between the walk and the read,
  and names that are not one step.

## What belongs here

A function every package that decides whether to trust a file by where it is, and how it is
reached, must compute alike: the models plugin (the models file), the kernel (the person's
startup file), memory (memory files outside the project, and in it through no link), the app
and brig (the XDG directories), agent (the project's `.git/HEAD`) and the extensions host (the
model's extensions). bh-02's plugins may import nothing of each other's, so a copy in each would
drift, and a drifted copy is a hole. It depends on the standard library alone: no cordis, no key, row
or bh-02 path. A function that names any of those stays in its plugin.

## The gate

`pyproject.toml` here keeps its own `[tool.pypeeker]` gate, run by `scripts/arch-check` with the
rest. Everything under `host_paths.*` is pure except the names in
`[tool.pypeeker.no-impure-functions].exclude`: `walked`, `roots` and `passes` read links and
resolve paths, and the opener opens and reads files, which is what they are for.
