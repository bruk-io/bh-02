---
id: TASK-0082
title: Let scripts/linux-jail-check build behind a TLS-intercepting proxy
status: Done
assignee:
  - '@claude'
created_date: '2026-10-11 16:19'
updated_date: '2026-10-11 17:26'
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
- [x] #1 With HTTP(S)_PROXY set and a CA bundle given (an option, or the bundle in SSL_CERT_FILE), the image builds and the container's uv, curl and apt trust that CA; the bwrap tests then run in the container
- [x] #2 With no proxy and no CA, the image builds from the same Dockerfile as before
- [x] #3 Neither the proxy's address nor any credential in it lands in the image: not in a layer, not in its history
- [x] #4 The script's docstring says how to run it behind such a proxy
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add --ca/SSL_CERT_FILE option; behind HTTPS_PROXY build with --network host, proxy as predefined build arg, CA as optional BuildKit secret (apt https sources + CaInfo; uv/curl env in RUN); run with host net, CA mounted ro, CA env vars. Proof: real run here.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
scripts/linux-jail-check only. Added --ca FILE (default SSL_CERT_FILE, used only with HTTPS_PROXY set; proxy without CA is an error that withholds the address). Behind a proxy: docker build --network host, HTTPS_PROXY as predefined build arg (not in history), CA as optional BuildKit secret (mode 0444, in no layer); Dockerfile RUNs switch apt sources to https with Acquire::https::CaInfo and export SSL_CERT_FILE/CURL_CA_BUNDLE for curl and uv python install; run uses --network host, CA mounted ro, HTTPS_PROXY by name, SSL_CERT_FILE/CURL_CA_BUNDLE/REQUESTS_CA_BUNDLE/GIT_SSL_CAINFO set. Evidence: (1) HTTPS_PROXY=http://127.0.0.1:42301 + SSL_CERT_FILE=/root/.ccr/ca-bundle.crt, scripts/linux-jail-check: image built, bwrap 0.9.0, uv 0.13.0, Python 3.15.0, 145 passed, 2 skipped in 40s, exit 0 (LINUX BASELINE: all green in container incl. brig bwrap tiers and bh-02 Linux jail tests). Unset SSL_CERT_FILE -> clear error. (2) No-proxy: same Dockerfile text parses and the optional secret is skipped; the build then fails at apt (exit 100) only because this container's default bridge has no network, so a full no-proxy build could not be proven here. (3) docker history --no-trunc: 0 hits for 127.0.0.1/42301/ca-bundle; docker save grep for 42301 or BEGIN CERTIFICATE: 0; container env has no proxy vars baked. (4) docstring section added. Not planted-failure tested: no safety test, a tooling script. scripts/check exit 1 on this root container: bh-02 jail tests in bh-02/app/tests/test_python_repl.py and runner-cordis-plugin test_runner_confined.py fail when run as root natively (HOME dotfiles in listings, placeholder 'held'), unrelated to this change, preexisting; format/lint/types/arch-check ok.

Fix round after review 1. dockerfile(proxy) is a pure function: with no proxy it returns the old DOCKERFILE constant; behind one it swaps the apt and uv steps (secret mounts, set -eu, https apt switch only there). AC2 evidence: cmp of dockerfile(None) vs the DOCKERFILE of f888300^ is byte-identical (empty diff); build_argv(None) == old argv, run_options(None) == [], docker_env(os.environ, None) == dict(os.environ). A real no-proxy build cannot run here (Docker's bridge has no network in this container). Also: ruff check --no-fix and ruff format --check on scripts/linux-jail-check clean; docker_env takes environ; docstring says BuildKit is needed only behind a proxy; not-a-file error names its source (SSL_CERT_FILE or --ca; seen: 'from SSL_CERT_FILE'). AC1 re-run behind proxy: 145 passed, 2 skipped in 39.55s, exit 0. AC3: docker history --no-trunc grep for 127.0.0.1/42301/ca-bundle = 0; docker save grep for 42301/BEGIN CERTIFICATE = 0. scripts/check not run, as asked.

Review 2 (2026-10-11, the reviewer who did not do the work): CLOSE, all four criteria met; it re-ran scripts/linux-jail-check behind the proxy (145 passed, 2 skipped, exit 0) and the docker history grep (0 hits). Should-fix taken by the orchestrator after review: DOCKERFILE is now built from its step constants (BASE_STEPS + APT_STEP + USER_STEPS + UV_STEP + WORKDIR_STEP) and dockerfile(proxy) swaps in the two proxy steps by composition, not str.replace, so a drifted constant can no longer make the proxy build silently fall back to plain-http apt with no CA, and the apt step is written once. Evidence: dockerfile(None) == the DOCKERFILE of f888300^ (True, byte for byte); dockerfile(proxy) == 0486831's dockerfile(proxy), which review 2 ran green (True); ruff check --no-fix and format --check on the file by name clean. Docstring reflowed under 110 columns. Kept on purpose: NO_PROXY stays out of the container; the file's names stay public, as its existing ones are.
<!-- SECTION:NOTES:END -->
