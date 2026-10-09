# host-paths

Paths as bh-02's own process must judge them when the model can write some of them. `README.md`
says what each name is; this file is where things go and what the gate holds.

## Layout

- `src/host_paths/paths.py`: `config_home`, `state_home`, `walked`, `MOST_LINKS`, `roots` and
  `passes`. `__init__.py` only re-exports.
- `tests/test_host_paths.py`: the XDG directories (an empty or relative value is unset), the walk
  against a table of links in a temporary directory (absolute, relative, the file itself, `..`
  after a link, dangling, missing, a loop that ends at `MOST_LINKS`), and `passes` over roots as
  named and as resolved.

## What belongs here

A function every package that decides whether to trust a file by where it is, and how it is
reached, must compute alike: the models plugin (the models file), the kernel (the person's
startup file), memory (memory files outside the project), the app and brig (the XDG
directories). bh-02's plugins may import nothing of each other's, so a copy in each would drift,
and a drifted copy is a hole. It depends on the standard library alone: no cordis, no key, row
or bh-02 path. A function that names any of those stays in its plugin.

## The gate

`pyproject.toml` here keeps its own `[tool.pypeeker]` gate, run by `scripts/arch-check` with the
rest. Everything under `host_paths.*` is pure except the names in
`[tool.pypeeker.no-impure-functions].exclude`: `walked`, `roots` and `passes` read links and
resolve paths, which is what they are for.
