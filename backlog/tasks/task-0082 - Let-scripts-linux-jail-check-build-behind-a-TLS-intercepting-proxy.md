---
id: TASK-0082
title: Let scripts/linux-jail-check build behind a TLS-intercepting proxy
status: To Do
assignee: []
created_date: '2026-10-11 16:19'
labels:
  - tooling
  - size-2
dependencies: []
priority: high
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scripts/linux-jail-check builds its image from a fixed Dockerfile that downloads over the network (apt, astral.sh's installer, uv's Python), and here every outbound connection goes through a proxy that re-signs TLS with its own CA. The build container gets neither the proxy settings nor the CA, so the build fails at apt-get (found by TASK-0075's worker, 2026-10-11), and every task whose finish line names this check can't meet it. Unprivileged native runs under tini (a `tester` user) are the stand-in until this lands.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 With HTTP(S)_PROXY set and a CA bundle given (an option, or the bundle in SSL_CERT_FILE), the image builds and the container's uv, curl and apt trust that CA; the bwrap tests then run in the container
- [ ] #2 With no proxy and no CA, the image builds from the same Dockerfile as before
- [ ] #3 Neither the proxy's address nor any credential in it lands in the image: not in a layer, not in its history
- [ ] #4 The script's docstring says how to run it behind such a proxy
<!-- AC:END -->
