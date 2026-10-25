---
id: DRAFT-0018
title: pyproject lists src paths for three plugins that are not in the repo
status: Draft
assignee: []
created_date: '2026-10-25 19:05'
labels: []
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-0169.03's commit 0bb97d4 added bh-02/plugins/{brig,context,kernel}-cordis-plugin/{src,tests} to [tool.pypeeker].src in the root pyproject.toml. scripts/arch-check writes that list from the [tool.arch-check].src globs, and in this working tree those three directories still exist holding only __pycache__ from plugins that were removed, so the glob matched them and the generated list was committed. git ls-files knows no file under any of them. In this checkout the consequence is that 'uv run mypy' (and so scripts/check's types step over the whole workspace) fails with "There are no .py[i] files in directory 'bh-02/plugins/brig-cordis-plugin/src'"; on a fresh checkout the three paths in [tool.pypeeker].src name directories that do not exist at all. Evidence: git show 0bb97d4 -- pyproject.toml; find bh-02/plugins/brig-cordis-plugin.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The root pyproject.toml's [tool.pypeeker].src names only paths that exist in a fresh checkout
- [ ] #2 uv run mypy and scripts/check run over the whole workspace without failing on a directory that holds no .py files
<!-- AC:END -->
