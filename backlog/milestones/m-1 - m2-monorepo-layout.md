---
id: m-1
title: "M2 Monorepo layout"
---

## Description

Arrange the repo by ownership: bh-02/ (the app) with bh-02/plugins/, examples/warden with its plugins, libs/ (cordis, cordis-helpers, brig). Member lists derived from directory globs, not kept by hand; cross-package gate rules at the root, each library's internal layering and purity budget with it; one scripts/check; root CLAUDE.md a map with per-area docs.
