# brig

A standalone sandbox library (spec -> mechanisms -> stack -> launcher -> handle, every axis of
enforcement graded). `README.md`, `SPEC.md`, `WORKFLOW.md` and `MILESTONES.md` are its docs.

- It imports the standard library and itself, nothing else: no cordis, no app, no plugin. A
  plugin that jails something imports brig (only `brig_cordis_plugin`, by the root gate's
  `brig-one-adapter`); brig never imports back.
- Its own gate: `[tool.pypeeker]` in `pyproject.toml` here, rules in `pypeeker_rules/brig.py`
  (`brig-layers`, the layer DAG of SPEC.md section 13, and `brig-standalone`), run by
  `scripts/arch-check`. The workspace's house rules (re-export-only `__init__`,
  `under-exposed-access`, ...) don't apply to it.
- Its suite is the one exception to "no `sys.path` changes": it imports its own helpers as
  `tests.conftest` / `tests.unit.strategies`, so the root pytest config has
  `pythonpath = ["libs/brig"]`. Every test carries exactly one tier marker (`unit`,
  `integration`, `e2e`), which `tests/conftest.py` enforces for brig's tests only. The full
  suite takes about three minutes; `uv run pytest libs/brig -m unit -q` is the quick loop.
