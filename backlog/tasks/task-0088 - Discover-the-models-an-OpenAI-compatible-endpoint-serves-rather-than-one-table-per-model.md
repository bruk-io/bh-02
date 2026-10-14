---
id: TASK-0088
title: >-
  Discover the models an OpenAI-compatible endpoint serves, rather than one
  table per model
status: Done
assignee:
  - '@claude'
created_date: '2026-10-13 22:33'
updated_date: '2026-10-14 10:40'
labels:
  - models
  - size-3
dependencies: []
priority: medium
type: feature
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Asked by the owner (2026-10-13), who runs a local OpenAI-compatible server. Today each model is a table in ~/.config/bh-02/models.toml with a fixed id. Proposal, design first: a table with discover = true is an endpoint (provider openai, base_url, optional key) and names models ENDPOINT/ID. Resolution stays pure: ENDPOINT/ID needs no network (the table gives provider, base_url and key; the id is the rest), so models:model neither waits on nor fails at a server being up, and an id the server lacks is the first step's 404 as now. Discovery is listing only: models:catalog (the models value, already read fresh each time asked) asks GET {base_url}/models when /model lists, off the event loop with a short timeout, an unreachable endpoint shown as one line, never an error; the status bar never triggers it. No new row or key: models:switch depends on models, not model, so listing never reloads the model in use, and choosing a discovered model writes default = "ENDPOINT/ID" into the session's layer as now. The HTTP call behind a small Protocol faked in tests; parsing the /models reply a pure function. Trust: endpoints only from the trusted models file (never the project); the key only in the request's header; ids are the server's text, shown with control characters stripped, never a path or an argument; only the person picks a model. Open: a name rule for ids holding / or : (split at the first /); a filter for endpoints listing hundreds (include = ["qwen*"]); a short per-endpoint cache. Pairs with the models-file default ticket (default = "local/qwen2.5-coder").
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A models-file table with discover = true lists, under /model, every model its endpoint's GET /models returns, named ENDPOINT/ID; an unreachable endpoint is one line saying so, within a short timeout, off the event loop
- [x] #2 ENDPOINT/ID resolves with no network call, by --model, /model and a layer's default; the model row never waits on discovery; a test
- [x] #3 Ids from the server are shown with control characters stripped and never used as a path or an argument; the key is sent only in the request's header; endpoints are read only from the trusted models file; a test of each
- [x] #4 An optional include filter narrows what is listed; the status bar never triggers discovery
- [x] #5 docs/bh-02/using/models.md, the models plugin's README and CONTRACTS.md (if the models value's shape changes) describe it; scripts/check passes
- [x] #6 /model's choices (models switch.py _choices), which the palette calls on every key and the composer's completion list once per opening, on the TUI's event loop, never trigger discovery: they read a cached list of discovered models, filled off the loop (decision-0003)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
DESIGN (no code yet; waiting for the orchestrator's accept or changes). Shape: no new row or key. models:catalog gains a small cache and two methods (refresh, endpoints); models:model is untouched and has no way to reach the network.

1. TABLES. discover = true on an openai table of the models file makes it an endpoint: base_url, optional key, max_tokens and temperature (inherited by its models). It has no id (an id beside discover is that table's problem: the endpoint is not itself a model; --model local says "local is an endpoint; name one of its models, local/ID, /model lists them"). include = a list of non-empty strings; discover must be a bool; include without discover is a problem; an endpoint's name may not hold "/". discover in the row's extra (a layer) is a problem and discovers nothing: endpoints come only from the trusted models file (one in the project is already not read, so it gives none).

2. NAMES. ENDPOINT/ID is split at the FIRST "/": the endpoint is the text before it, the id everything after (it may hold "/", ":", "@": local/Qwen/Qwen2.5-Coder:7b, or:anthropic/claude-sonnet-4:free). An exact table name wins first (a quoted ["a/b"] plain model still works). One pure named.find(name, models) -> Named | None serves chosen, check, current and listed, so the status bar shows "local/qwen (openai)" with no network. Derived Named: the endpoint's table minus discover/include, provider openai, id = the rest, source = the endpoint's. Resolution stays pure: no fetcher exists in providers.resolved/opened. An id the server lacks is the first step's 404, as now.
 Which listed ids become names (they are the server's text): control characters (C0, DEL, C1, as palette_entries strips them) are removed; an id is listed only if what remains is 1-200 printable ASCII with no space. Why: /model NAME is one word, and a non-BMP character in a name makes cordis's format_layer write invalid TOML (checked: json.dumps emits a surrogate pair, tomllib rejects it), so choosing it would break the session's layer. Ids not listed are counted in one line. A name the person types by hand is not restricted, as today.

3. include. fnmatch globs (* ? [ab]), case-sensitive, tested on the id (the part after ENDPOINT/), listed if any pattern matches; applied at READ time to the cached ids, so editing it needs no refetch. Display cap 200 per endpoint ("N more: narrow with include"); the cache keeps at most 2000 ids from a body of at most 1 MiB.

4. CACHE. Lives in the catalog row (class Discovery, openai/discovery.py), keyed by (base_url, key LINE NAME): ids only, never the key; entries for endpoints no longer in the file are dropped at each refresh. Filled ONLY by Catalog.refresh(), an async method that /model (no args) awaits in its own coroutine: one GET {base_url}/models per endpoint, concurrently, through async httpx2 (never a sync call on the loop; no thread, so nothing holds bh-02 open at exit), connect timeout 3 s, whole request 6 s (asyncio.timeout), redirects not followed (a key never follows one), body at most 1 MiB. Expiry: refresh skips an endpoint listed OK less than 30 s ago (retyping /model does not hammer a hosted endpoint); a failure is never fresh, so retyping /model after starting the server retries at once. READS never expire: listed() and the choices serve what the last refresh found (stale ids are suggestions; resolution never depends on them); a refresh that fails drops that endpoint's ids. Nothing but /model fills it: not choices, not the composer's completion, not the status bar, not startup. So completion offers discovered models after one /model.

5. /model's LIST. models.listed() (sync, cache only) adds discovered entries after the extras, per endpoint, ids sorted: {name, provider "openai", id, current, where}; the current model and the standing default, when they are ENDPOINT/ID names, are listed even if the cache lacks them (so the marks always show). New models.endpoints() (sync): per endpoint the facts that have no model row: why (no list: connection refused / no answer within 6 s / 401 or 403 "refused the key" / 404 "no /models" / other status / not an OpenAI model list / key line missing from local.env / the table's problem), more, skipped, none matched. model_list prints one indented line each after the models, before the footer, e.g. "far: no list from http://far:8080/v1/models (connection refused); is it running? Its models are not listed." Never an error, never the server's body (any library text goes through wire.scrubbed and a control strip). switch._choices keeps its code (it reads listed()): discovered models are offered from the cache, with a comment saying it must never discover.

6. THE HTTP PROTOCOL AND ITS FAKE. openai/discovery.Get: async __call__(url, headers) -> Reply | Down (frozen dataclasses: Reply(status, body: bytes), Down(why)); httpx_get is the real one (impure edge). FakeGet in openai/testing.py (records url+headers, canned replies, an optional gate to hold a reply). StubServer gains GET /v1/models (served ids, key check, delay) for the real-socket tests. Parsing is pure: read_listing(Reply | Down) -> Listed | Unlisted (match + assert_never), matching, usable_id, models_url. The key is read by the existing openai.authorization (header only, withheld rule included).

7. TESTS, each trust criterion SEEN FAILING with its guard removed:
 - ids: ESC/BEL/space/non-ASCII/over-long ids -> plant: drop the cleaning -> an ESC byte reaches /model's text.
 - id never a path or argument: ids "../../x", "--flag", "$(x)" are listed and chosen; set_model round-trips each through tomllib as one string; the request URL is always base/models; cwd unchanged; the id appears only as the body's "model". Plant: build a URL from an id.
 - key only in the header: FakeGet sees it in headers only; absent from the URL, the list text, endpoints(), repr of Discovery/headers, and a reply that echoes it. Plant: key in the URL query.
 - endpoints only from the trusted file: a file in the project -> zero fetches; discover in extra -> zero fetches and a problem. Plant: drop the in_project refusal; drop the source check.
 - AC2: resolved/opened/check/current for local/x:7b, a layer default, --model (sessions.create passes it verbatim) and /model: StubServer saw zero GETs; the model row streams a step with id x:7b. Plant: chosen asks for a refresh.
 - AC6/AC4: choices, listed, current with an empty cache never call Get (the loop is given a turn after); plant: _choices schedules a refresh task.
 - off the loop: a ticker keeps ticking while a slow StubServer GET is awaited; unreachable port = one line within the deadline; plant: a sync urllib call.
 - parsing, include, cap, expiry (an injected clock), a failure replaces cached ids, concurrent /model calls share one refresh.

8. FILES. named.py (find, endpoint rules, problem), openai/listing.py (pure) and openai/discovery.py (new), openai/testing.py, openai/__init__.py, catalog.py (cache, listed, endpoints, refresh; check/current via find), providers.py (resolved via find), switch.py (Models Protocol grows refresh/endpoints; run awaits refresh; model_list lines), tests (new test_openai_listing.py, test_models_discovery.py; test_models_switch.py's fake grows; test_named_models.py), docs: docs/bh-02/using/models.md, the plugin README, CONTRACTS.md (models row), GLOSSARY.md (endpoint, discover), the app README if it lists /model; root pyproject purity budget (Discovery.refresh, httpx_get, Catalog.refresh/endpoints, each with its reason). No brig, no spec change.

9. RISKS AND SIZE. The Models Protocol grows, so the switch test fake is updated. Fits size-3 (one plugin, about 250 lines of source, about 300 of tests, docs): no split. Follow-up to file after acceptance: cordis's format_layer writes a non-BMP character as an invalid TOML surrogate escape (a bug beyond this task; here discovery only lists ASCII ids). ORDER: pure parts and their tests (named.find, listing), then discovery and the fakes, then catalog and switch, then docs, then the full checks (models plugin tests, bh-02/app/tests, arch-check, mypy, scripts/check, as root without tini).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Finish-line change to AC #1 (accepted by the orchestrator 2026-10-14, AC text left as written): AC #1 now lists every id that is printable ASCII with no space (1-200 characters, control characters stripped first); ids that are not are counted in one line, not listed. Why: cordis's format_layer writes a non-BMP character as a surrogate-pair escape, which is invalid TOML (checked: tomllib rejects it), so choosing such a name with /model would write a session layer the loader can't read; /model NAME is also one word, so an id with a space can't be typed.

BUILT as planned (plan accepted 2026-10-14 with the changes: the listed-ids rule kept, TTL 30 s and the caps kept, the TASK-0087 pairing test added, the purity budget only for I/O, the format_layer follow-up filed).

WHAT CHANGED. named.py: `endpoint`, `derived`, `find` (the one pure rule: exact table name, else ENDPOINT/ID split at the first "/"), `not_a_model`, `said_names`; `discover`/`include` are openai keys with their problems (bool; include a non-empty list of non-empty strings; no id; no "/" in the name; discover in a layer's `extra` refused). New openai/listing.py (pure: Reply, Down, Listed, Unlisted, models_url, cleaned, usable, read_listing, matching, notes) and openai/discovery.py (the `Get` Protocol, `httpx_get`, `Discovery` cache, `Ask`). catalog.py: `refresh()` (async), `endpoints()`, `listed()` adds each endpoint's cached models and the current/default ENDPOINT/ID model; `check`/`current` go through `find`. switch.py: `Models` Protocol gains `refresh` and `endpoints`; `/model` (no args) awaits `refresh`, `model_list` prints each endpoint's notes; `_choices` unchanged in code and documented as never discovering. openai/testing.py: `FakeGet`, StubServer `GET /v1/models` (models, delay) and a `method` on every kept request. Root pyproject purity budget: Catalog.endpoints, Catalog.refresh, _ask, httpx_get (each with its reason). Docs: docs/bh-02/using/models.md, the plugin README, CONTRACTS.md (models row), GLOSSARY.md (endpoint). Follow-up filed: TASK-0094 (format_layer writes a non-BMP character as invalid TOML; not sized).

FINISH-LINE CHANGE TO AC #1 (accepted by the orchestrator 2026-10-14, AC text left as written): it lists every id that is printable ASCII without a space (1-200 characters, control characters stripped first) and counts the rest in one line (see the earlier note: format_layer would write a non-BMP name as invalid TOML).

EVIDENCE (root, no tini, foreground, one run at a time; arch-check and scripts/check were moved to the background by the tool's time limit and waited for, nothing else ran meanwhile):
- uv run pytest bh-02/plugins/models-cordis-plugin -q: 249 passed, 2 skipped (was 174; new: test_openai_listing.py 29, test_models_discover_names.py 21, test_models_discovery.py 15, test_models_discovery_wire.py 9, one switch test).
- uv run pytest bh-02/app/tests -q: 200 passed, 1 skipped (includes the new TASK-0087 pairing test in test_session_dirs.py: models file default = "local/x:7b" over an endpoint; sessions.create records it in the layer and meta stack; the model row resolves it and runs a step; StubServer saw one POST and zero GETs).
- scripts/arch-check --no-fix: exit 0 (after the budget entries; the first run named exactly Catalog.endpoints, Catalog.refresh and _ask, and nothing else). uv run mypy: exit 0 (187 files). scripts/check: exit 0 (2688 passed, 31 skipped in 7m17s; format, lint, types, gates, docs ok; tokens skipped: no bh-01).
- Not verified: scripts/linux-jail-check (not relevant); a hand run of /model against a real local server or a hosted one (the stub server and httpx2.MockTransport stand in); no real-launch pty test of /model with an endpoint.

PLANTED VIOLATIONS, each seen failing with its guard removed, then restored (cmp'd against a copy):
- A: control-character stripping removed -> test_control_characters_are_stripped_before_an_id_is_judged and test_a_server_s_ids_are_shown_with_control_characters_stripped failed; with the ASCII rule removed too (A2), the ESC byte reached /model's text (the no-control-character assertion failed).
- B: an id used in a request URL (a GET per listed id) -> several tests failed (the URL asked is no longer only base_url/models).
- C: the key put in the URL's query -> at least 8 tests failed (test_the_key_goes_in_the_request_s_header_and_nowhere_else among them). C2: the scrub of a failure's text removed -> that test failed (the key shown).
- D1: a models file in the project read anyway -> test_endpoints_come_only_from_the_trusted_models_file failed. D2: `endpoint` ignoring a layer's `extra` -> that test and test_discover_in_the_row_s_extra_is_no_endpoint... failed.
- E: Catalog.current() (the status bar's) scheduling a refresh -> test_a_model_of_an_endpoint_means_a_model_with_no_network_call and test_the_choices_and_the_status_bar_never_ask_a_server... failed. F: the choices scheduling a refresh -> the latter failed.
- G: a blocking urllib call in place of httpx_get -> test_asking_a_slow_server_does_not_block_the_event_loop failed (0 ticks, needs 25).
- H: the model row (providers.resolved) asking the endpoint for its list -> test_the_model_row_binds_an_endpoint_s_model_and_runs_a_step_with_no_listing_asked and the app's TASK-0087 pairing test failed.

ACCEPTANCE: #1 test_model_lists_what_each_endpoint_serves_named_endpoint_slash_id, test_the_real_get_lists_what_a_server_serves, test_an_unreachable_endpoint_is_one_line_within_the_deadline_never_an_error, test_a_server_that_does_not_answer_in_time_is_said_at_the_deadline (6 s deadline, 3 s connect), test_asking_a_slow_server_does_not_block_the_event_loop. #2 test_a_model_of_an_endpoint_means_a_model_with_no_network_call (--model/layer default/the file's default/check/current/listed/endpoints/`/model NAME`, zero Get calls), the wire test of the model row, the app pairing test. #3 the ids, key and trusted-file tests above (A-D). #4 test_include_narrows_what_is_listed_from_what_was_kept and E. #5 docs, README, CONTRACTS, GLOSSARY, scripts/check exit 0. #6 test_the_choices_and_the_status_bar_never_ask_a_server_and_offer_what_model_found and F.

Close review (Opus low, independent): CLOSE, no blocking findings; AC #1 judged against the orchestrator's narrowed finish line. The reviewer planted nine faults in a scratch copy (cleaning dropped, key in the URL, project models file read, current() and _choices scheduling a refresh, the model row GETting /models, redirects followed, a failed refresh counted fresh, the 1 MiB limit removed) and each was caught. Runs: models 249 passed, app 200 passed; arch-check, mypy, scripts/check (2688 passed) exit 0. Should-fix and nits filed as TASK-0095 (not blocking). Not verified by anyone: /model against a real server (the stub and MockTransport stand in).
<!-- SECTION:NOTES:END -->
