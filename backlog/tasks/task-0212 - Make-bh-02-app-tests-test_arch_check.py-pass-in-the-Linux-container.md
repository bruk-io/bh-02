---
id: TASK-0212
title: Make bh-02/app/tests/test_arch_check.py pass in the Linux container
status: Done
assignee: []
created_date: '2026-11-07 22:31'
updated_date: '2026-11-08 18:26'
labels:
  - app
  - size-1
dependencies: []
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Run in the scripts/linux-jail-check container, serially, as the unprivileged user under tini, 25 of its 40 tests fail: the output that scripts/arch-check prints is empty where a pypeeker report or an index line is expected, and exits are 1 where 0 is expected. On the Mac they pass. The test loads only scripts/arch-check and the standard library. Seen while doing TASK-0079.31, whose diff it cannot reach.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Why the 25 fail in the container is found and said in the notes
- [x] #2 The file passes in scripts/linux-jail-check run on it alone, or skips there by name saying why
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause: pypeeker segfaults (exit 139) in the container, in tree_sitter's own binding at Parser.parse, seen with PYTHONFAULTHANDLER and a five-line script with no pypeeker in it. tree-sitter 0.25.2 has no 3.15 wheel, so uv sync compiles it, and at the interpreter's -O3 under gcc 13 on aarch64 it crashes. Parsing works rebuilt at -O0, at -O2 -fno-strict-aliasing, at plain -O2 through the script, and on 0.26.0, which pypeeker caps out (tree-sitter<0.26). Which optimisation or which undefined behaviour is at fault was not found. Fix: ENV CFLAGS=-O2 in the image (scripts/linux-jail-check USER_STEPS). Evidence: scripts/linux-jail-check -- bh-02/app/tests/test_arch_check.py: 40 passed, exit 0; before, 25 failed, 15 passed. Any other Linux host building 0.25.2 with gcc at -O3 may hit the same crash; the lasting fix is pypeeker's cap, filed as a follow-up.

Check `scripts/check` exited 0

(62 earlier lines omitted)
```text
........................................................................ [ 87%]
........................................................................ [ 89%]
........................................................................ [ 91%]
........................................................................ [ 93%]
........................................................................ [ 94%]
........................................................................ [ 96%]
........................................................................ [ 98%]
................................................................         [100%]
3865 passed, 231 skipped in 73.04s (0:01:13)
   ok
== gates
== (root)
   ok
== libs/brig
   ok
== libs/cordis
   ok
== libs/cordis-helpers
   ok
== libs/host-paths
   ok
   ok
== docs
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: /Users/brukhabtu/src/github.com/bruk-io/bh-02/site
INFO    -  Documentation built in 1.34 seconds
   ok
== tokens
bh-01's tokens and bh-02's theme are in sync
   ok
```

Repro at c5b001f4860c, test files: scripts/linux-jail-check; command: `scripts/linux-jail-check --shell 'env -u CFLAGS uv pip install --quiet --reinstall --no-cache --no-deps tree-sitter==0.25.2; .venv/bin/pytest bh-02/app/tests/test_arch_check.py -q -p no:cacheprovider --tb=no 2>&1 | tail -1; exit ${PIPESTATUS[0]}'` exited 1

```text
== image bh-02-linux-jail (ubuntu 24.04, bubblewrap, uv, Python 3.15)
sha256:fa17ee764268fa1a5e0c664562c988baeed0af488a99326031ef01efb5b225aa
== env -u CFLAGS uv pip install --quiet --reinstall --no-cache --no-deps tree-sitter==0.25.2; .venv/bin/pytest bh-02/app/tests/test_arch_check.py -q -p no:cacheprovider --tb=no 2>&1 | tail -1; exit ${PIPESTATUS[0]}
bubblewrap 0.9.0
uv 0.13.7 (aarch64-unknown-linux-gnu)
Python 3.15.2 (main, Oct 26 2026, 14:08:24) [Clang 23.1.3 ]
25 failed, 15 passed in 6.85s
```

Closed by review. Both criteria met. Reproduced independently in the container, rebuilding tree-sitter 0.25.2 from source with --no-cache: without CFLAGS (sysconfig OPT -O3) parsing exits 139 and test_arch_check.py gives 25 failed, 15 passed; with CFLAGS=-O2 parsing works and it gives 40 passed. The named command as committed: 40 passed. scripts/check exited 0. The repro was recorded after the fix, so it undoes the flag inside the container; it fails only because that command removes the fix. Findings, none filed: (1) low: -O2 is a workaround and the undefined behaviour was not found, so the flag can hide rather than cure it; other Linux hosts stay exposed; already TASK-0213. (2) low: only aarch64 was measured, and x86_64 was not tried. Answered here. Not run by this review: the default linux-jail-check suite, and the notes' -O0, -fno-strict-aliasing and 0.26.0 measurements.
<!-- SECTION:NOTES:END -->
