---
id: TASK-0095
title: >-
  Refuse an ENDPOINT/ID name when its endpoint table has a problem, and tidy
  discovery's edges
status: Done
assignee:
  - '@claude'
created_date: '2026-10-14 10:40'
updated_date: '2026-10-14 12:02'
labels:
  - models
  - size-2
dependencies: []
priority: low
type: bug
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Filed from TASK-0088's close review (should-fix and nits, not blocking). Should-fix: named.find (named.py ~704-717) and not_a_model (~720) derive a model for ENDPOINT/ID even when the endpoint's table has a problem (e.g. both id and discover = true, or a bad include): problem(host) reports it and listed/endpoints skip the table, yet --model, /model and a layer's default resolve through it. No network or trust impact; the person just gets a model from a table bh-02 calls broken. Fix: find/derived check problem(host) and the resolution says the table's problem with what to write. Nits: discovery.py ~89-94 checks the 1 MiB limit after appending a chunk (up to one chunk more is held); discovery.py ~96-101 lets an exception outside the caught set (UnicodeEncodeError from a non-ASCII key value in local.env, put in a header) out of refresh into /model, against its docstring's 'never raises for a server'; listing.py ~278 counts entries that are not dicts or have no id as 'ids not listed'.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 --model, /model and a layer default naming ENDPOINT/ID on an endpoint table with a problem are refused with that problem and what to write (models-file house style), and bh-02 still starts; a test, seen failing before the fix
- [x] #2 A key line in local.env that cannot go in a header gives one line under /model's list, not an exception out of /model; a test
- [x] #3 The body limit stops before holding more than 1 MiB, and the not-listed count says what it counts; scripts/check passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
ORDER: (1) tests first, each seen failing on today's code, then the fix: (a) named.py: derived() returns the endpoint's own table when problem(host) is not None, so find() means that table and not_a_model() says its problem (problem first, before 'is an endpoint'); tests for --model / a layer's default / the models file's default (resolved, opened -> Unusable, bh-02 still starts), /model NAME (Catalog.check and Switch.run) and the status bar (current), each over every kind of endpoint problem; seen failing with the problem(host) check removed from derived. (b) openai/client.py authorization(): a key line that is not printable ASCII is a ModelsError naming the line (never its value) -> _ask turns it into the endpoint's one line; a wire test over real httpx_get + StubServer (today: UnicodeEncodeError out of refresh) seen failing before. (c) discovery.httpx_get: check len(body)+len(chunk) > BODY_LIMIT before appending; a test with chunks just over the limit that spies on the buffer's peak size (the outcome is a Down either way; only the memory held differs), seen failing before. (d) listing.notes: the count says 'entries not listed' (an entry with no id, or an id a name can't carry); docs/README wording updated. RISKS: authorization() is shared with the model row's own step, so a non-ASCII key now gives a ModelsError there instead of UnicodeEncodeError (same root cause; stated in the notes, no scope beyond that). PROOF: models plugin tests, uv run pytest bh-02/app/tests -q, scripts/arch-check, uv run mypy, scripts/check as root without tini, exit codes read directly; each planted guard removed and restored (cmp against a copy).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
WHAT CHANGED (models plugin only; no brig, no spec). named.py: derived() returns the endpoint's own table when problem(host) is not None (find goes through it), and not_a_model() says problem(found) first, then 'is an endpoint', so --model / /model NAME / a layer's default / the models file's default naming ENDPOINT/ID on a broken endpoint table are refused as a ModelsError(model_config) carrying the table's problem and what to write ('model local (FILE): an endpoint names no id, it lists its models (named local/ID). Remove id, or remove discover for a single model'); the model row binds Unusable, so bh-02 starts and each step says it; the status bar (current) shows the name with no provider. openai/client.py authorization(): a key line that is not printable ASCII is a ModelsError(authentication_failed) naming the key and the file, never the value; _ask already turns a ModelsError into the endpoint's one line, so /model lists 'local: no list from URL (model local names the key LOCAL_KEY, whose line in FILE holds a character a request header can't carry (a key is printable ASCII). Fix that line, then try again.); its models are not listed' and no request is made. Side effect, same root cause: authorization is the model row's too, so a non-ASCII key now gives that ModelsError at a step instead of httpx2's UnicodeEncodeError. openai/discovery.py httpx_get: len(body)+len(chunk) > BODY_LIMIT is checked before the chunk is appended. openai/listing.py: the count is now '{N} entries not listed: a model here needs an id of printable ASCII without a space, at most 200 characters' ('1 entry'); Listed.skipped's docstring says it counts entries (no id, or an unusable one). Docs: plugin README, docs/bh-02/using/models.md, named.py docstring. CONTRACTS.md: no shape changed.
TESTS (new): test_models_discover_names.py parametrized over 5 kinds of endpoint problem (find/derived/not_a_model/chosen); test_models_discovery.py a layer default + opened/Unusable, the models-file default, /model NAME (check + Switch.run, layer untouched) + current(); bh-02/app/tests/test_session_dirs.py --model through sessions.create + opened; test_models_discovery_wire.py the key line over real httpx_get + StubServer (two keys: non-ASCII, tab) and the body limit; test_named_models.py authorization over 4 unsendable keys; test_openai_listing.py/test_models_discovery.py the new wording.
SEEN FAILING BEFORE THE FIX (today's code, same tests): AC1: 8 failed in the models tests (DID NOT RAISE ModelsError; check('local/x:7b') was None) + the app --model test (DID NOT RAISE: the step ran against the stub). AC2: UnicodeEncodeError: 'ascii' codec can't encode character 'xe9' out of /model's refresh (the wire test). AC3: the spy on the body buffer saw 1048577 bytes held for a 1 MiB+1 answer (the Down is the same either way, so a buffer double records what was held; asserts max <= BODY_LIMIT, and that the spy was used).
PLANTED AFTER THE FIX, restored and cmp'd against copies: derived without the problem(host) check -> 9 failed (all of the above); authorization without the printable-ASCII guard -> 5 failed (wire + 4 unit); httpx_get back to check-after-append -> the body-limit test failed.
RUNS (root, no tini, foreground, one at a time; exit codes read from the shell, not through a pipe): uv run pytest bh-02/plugins/models-cordis-plugin -q: exit 0, 262 passed, 2 skipped (was 249/2); uv run pytest bh-02/app/tests -q: exit 0, 201 passed, 1 skipped (was 200); scripts/arch-check --no-fix: exit 0; uv run mypy: exit 0 (187 files); scripts/check: exit 0 (2705 passed, 31 skipped, 7m15s; format, lint, types, gates, docs ok; tokens skipped: no bh-01). scripts/check outlived the tool's 600 s foreground limit and was moved to the background by the tool; I waited for it in the same turn (tail --pid), nothing else ran meanwhile. Not verified: /model against a real hosted or local server (StubServer and httpx2.MockTransport stand in), scripts/linux-jail-check (not relevant).

Close review (Opus low, independent): CLOSE, no blocking findings. Planted in a scratch copy: problem(host) check removed (9 fail), the printable-ASCII key guard removed (5 fail), the 1 MiB check after the append (the buffer-spy test fails). The key's value is in no message; the chat row gets a Recoverable ModelsError(authentication_failed) that says what to do. Runs: models 262, app 201 passed; arch-check, mypy exit 0; scripts/check's steps all ok (2705 passed; the reviewer's run hit its time cap after tests, gates and docs then run alone, exit 0). Should-fix (no test that /model NAME of another, valid model still switches while an endpoint table is broken) added to TASK-0093 as AC; nits noted there.
<!-- SECTION:NOTES:END -->
