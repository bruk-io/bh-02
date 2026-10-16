---
id: TASK-0122
title: Make the docs' strict build fail on a link to an anchor that is not there
status: Done
assignee:
  - '@claude'
created_date: '2026-10-16 13:35'
updated_date: '2026-10-16 22:02'
labels:
  - docs
  - size-1
dependencies: []
priority: low
type: task
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by TASK-0104.02: a planted link to a missing anchor in a README (`[old](#detached-and-on-the-subscription-only)`) left `mkdocs build --strict` at exit 0 with only an INFO line, because mkdocs.yml sets no `validation.links.anchors` and mkdocs 1.6 defaults it to info. So scripts/check's docs step, the one definition of green, passes a broken anchor. Setting `validation: links: anchors: warn` makes --strict fail on it; first see what the existing docs would fail on, and fix those in the same change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 scripts/check's docs step fails on a link to a missing anchor, shown by a planted link seen failing and then removed
- [x] #2 The docs as they are build clean under that setting, any broken anchors it finds fixed in the same change
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. mkdocs.yml: add validation: links: anchors: warn (mkdocs 1.6), with a comment saying why. Baseline strict build (before the change) was exit 0 with no warnings.
2. Run uv run mkdocs build --strict: list every anchor warning (page, link, missing anchor). Each is a broken link; fix it by pointing the link's fragment at the heading that exists (the heading's slug as mkdocs/toc makes it). Edit only link targets, never headings (TASK-0121 is rewording pages). Links inside included READMEs are fixed in the README source, which the hook rewrites onto the page; check the README's own link too.
3. Planted check: add a link to a missing anchor on a page, run the strict build, see it exit non-zero with a warning naming it; remove it, rebuild, exit 0.
4. Proof: uv run mkdocs build --strict exit 0; scripts/check bh-02/app --no-gates (its docs step is that build) once at the end; scripts/arch-check --no-fix once (docs changed, outside a member).
5. Commit one commit: reset --soft to d552a08, message with the attribution lines. Risks: a README edit lives in a member, so note that in the report; a fix that points at a heading that is renamed by TASK-0121 would break (it is told not to rename).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed: mkdocs.yml only (6 lines): validation: links: anchors: warn, with a comment on why. No link was edited: the docs have no broken anchor. Before the change uv run mkdocs build --strict exit 0 with only INFO lines; after it, exit 0 with no WARNING.
Planted 1 (docs/index.md, two links to missing anchors: bh-02/get-started.md#no-such-heading and #no-such-heading): uv run mkdocs build --strict exit 1, two WARNINGs, Aborted with 2 warnings in strict mode. Reverted with git checkout, rebuild exit 0.
Planted 2 (the TASK-0104.02 case: libs/host-paths/README.md with a link to #detached-and-on-the-subscription-only, included on cordis/host-paths.md): strict build exit 1, WARNING: Doc file cordis/host-paths.md contains a link #detached-and-on-the-subscription-only, but there is no such anchor on this page. Reverted.
Planted 3, the docs step itself: scripts/check bh-02/app --no-gates with the planted README link: exit 1, "== docs" FAILED: docs (format, lint, types and tests ok). Reverted.
Guard removed: Planted 1 with the setting taken out (HEAD mkdocs.yml) builds exit 0 with two INFO lines, the original behaviour. So the setting is what fails it.
Final: uv run mkdocs build --strict exit 0, no warnings. scripts/check bh-02/app --no-gates exit 0: format ok, lint ok, types ok (7 files), tests 238 passed 1 skipped, docs ok, tokens skipped (no ../bh-01/dist). scripts/arch-check --no-fix exit 0 (root, libs/brig, libs/cordis, libs/cordis-helpers, libs/host-paths all ok), run because mkdocs.yml is docs config outside a member.
Not verified: links the docs hook sends to GitHub are external, so mkdocs does not check their fragments. I grepped docs/ and the included sources for anchor links: every fragment link targets a site page or the same page; none goes to a repo file outside the site (no reference-style or HTML anchors either). The machine was shared; no timings recorded. The full scripts/check was not run.

Review: CLOSE. AC1 met: validation.links.anchors: warn is mkdocs 1.6's documented switch making missing anchors warnings, which --strict fails; worker record shows three plants exit 1 (incl. scripts/check docs step) and the guard-removed control exit 0. Reviewer did not re-plant (scratch copy blocked by review guardrail); relied on setting + record. AC2 met: reviewer ran uv run mkdocs build --strict at HEAD, exit 0, no warnings. Nit, not filed: fragments on links the docs hook sends to GitHub stay unchecked; none exist today per worker grep.
<!-- SECTION:NOTES:END -->
