# models-cordis-plugin

bh-02's model: named models over their providers, switched by name. Three rows:

| Row | Binds / registers | Consumes |
|---|---|---|
| `models:model` | `model`: one model step per `complete(messages, tools)` (CONTRACTS.md: model), the model `default` names on its provider | `host` (`credentials`: where `local.env` is looked for) |
| `models:catalog` | `models`: the models there are (an endpoint's, as `/model` last heard them), the one the model row names now, why a name can't be switched to, and why the models file is not read (CONTRACTS.md: models) | `loader`, `host` |
| `models:switch` | registers `/model [NAME]`: lists the models, switches by name in the session's layer, the reload queued in `jobs`; config: `layer` (the session's), `model_row` (`model`) | `commands` (`register`), `loader`, `models`, `jobs` (`put`) |

The model row's config (`ModelConfig`):
- `default`: the model's name; `--model` and `/model` set it. Unset (None) when no layer names a
  model: then the models file's `default` is the model, else none is chosen (below).
- `models`: the models file, when not the default one.
- `extra`: endpoints of the row's own, one table per name as in the file (a layer writes them),
  without `discover` or `key_command`, which only the models file may name.
- `state`, `env_file`, `cwd`: the claude-code provider's (below). `env_file` is also where the
  openai provider reads a model's key. Unset, `local.env` is looked for where the `host`
  value's `credentials` say (below). A models file must be outside `cwd` as well as the
  working directory (below).

## Named models

Two places name models, the second over the first (`named.py`, pure but for reading the file):
- the models file, `$XDG_CONFIG_HOME/bh-02/models.toml` (else `~/.config/bh-02/models.toml`);
- the row's `extra`.

There are no built-in models: every model is one an endpoint serves, so what a session runs on, and
what it spends, is always written down by the person. Claude on the subscription is a `claude-code`
endpoint naming Claude Code's aliases (`models = { sonnet = { id = "sonnet" } }`).

A later endpoint of the same name wins: `extra` over the file. The file is one table per
**endpoint**, a server and how to reach it, the same shape for every provider; its models are
under its `models`, each named `ENDPOINT/MODEL` (`named.derived`: the endpoint's settings with the
model's own over them):

```toml
[ollama]                                  # Ollama is an OpenAI-compatible endpoint at /v1
provider = "openai"
base_url = "http://localhost:11434/v1"
models = { llama = { id = "llama3.2" } }  # ollama/llama; inline, or as [ollama.models.llama]

[router]
provider = "openai"
base_url = "https://openrouter.ai/api/v1"
key = "OPENROUTER_API_KEY"                # a line of local.env, never the key itself
max_tokens = 4096                         # optional, sent only when set; its models share it

[router.models.sonnet]                    # router/sonnet
id = "anthropic/claude-sonnet-4"
temperature = 0.2                         # a model's own setting, over its endpoint's

[subscription]
provider = "claude-code"                  # no base_url: the subscription token
models.opus41 = { id = "claude-opus-4-1" }

[work]                                    # Claude through a gateway (below)
provider = "claude-code"
base_url = "https://gateway.example/anthropic"
key_command = "my-token-helper"           # Claude Code's apiKeyHelper
key_ttl_ms = 300000                       # optional
experimental_betas = false                # optional: for a gateway that refuses the beta headers
models.opus = { id = "claude-opus-5-5" }

[local-server]                            # also lists what its server serves, local-server/ID
provider = "openai"
discover = true
base_url = "http://localhost:1234/v1"
include = ["qwen*"]                       # optional: the ids matching one of these globs
```

A model's own table takes `id` and, for `openai`, `max_tokens` and `temperature`; everything about
reaching the server is its endpoint's. `ENDPOINT/ID`, an id the endpoint's `models` doesn't name, is
that id on the endpoint (`derived`), with no network. A table with an `id` of its own (the format
before endpoints) is that table's problem, which says how to move the id under its `models`. An
endpoint's name may not hold `/`.

A top-level `default = "NAME"` above the tables makes NAME the model a session starts on. The
model is chosen, lowest first, by the file's `default`, a layer's model row `default` (the
session's own layer, which `/model` and `--model` write; a layer that sets no `default` leaves the
file's in force: `ModelConfig.default` is None for none, `named.intended`), then `--model`. With
none of them, no model is chosen: the row binds `Unusable`, each step says `no model is chosen` with
the models there are and an endpoint and `default` to write (`named.chosen`), and the status bar
shows `none (unusable)`. So a resumed session keeps the model its
layer names, and `/model` and `--model` still switch. The app writes the model a new session
starts on into its layer when it creates it (`bh_02.sessions.create`: `--model`, else the file's
`default`; neither records none), so a session keeps it whatever the file says later; only a layer from
before that, naming none, follows the file's `default` as it is now (and `/model` of that name
there says "already"). The default chooses the spend, so it is read only where the tables are:
from a models file outside the project (below), never from one in it. The shell reads the file
itself, with the row's trust rule (`host_paths.passes` over the working directory and the
session's directory: the `cwd` `create` is given, which the CLI passes as the working directory)
and the row's reading of the `default` (`named.parsed`): the two cannot share a function (no
package imports another), so one app test (`test_session_dirs.py`) drives both over the same
files and fails if they disagree on what a new session starts on. The row also roots its check at
the model row's `cwd` when a layer sets one; the shell cannot see that, since a layer composes
after the session is created, and a `--patch` that sets the model row's config replaces the
session's whole (`pins_model`), so the pinned default goes with it. A `default` that is not a
name, or names no model, is a `ModelsError` naming the models file and what to write
(kind `models_file`, or `unknown_model`, which says it is the models file's `default` also when
the session's layer recorded it: `named.intended`), said at each step like any model that can't
be used (`Unusable`), while bh-02 starts and `/model NAME` fixes it; it is not looked at while a
layer names a model. The shell never hides it: for a default that is not a name (a number, an
empty string, a list), and for a file that is not TOML, is not UTF-8 text, has a key that is no
table, or can't be read, it records no model in the new session's layer (its `stack` in
`bh-02 sessions` is `default`), so the row's error shows; a default that names no model is a name,
and is recorded.
A `[default]` table is an endpoint named `default`.

**A models file that can't be read** (not TOML, not UTF-8 text, a key that is no table, a path that
is no file) is not a failure of the row: `known` names the row's `extra` behind it, as behind a
file refused in the project, with `why` saying what is wrong and what to do. A layer's choice of an `extra` model
runs; a row no layer names a model for has no default to follow, so it says the file's problem
(`resolution`). `Catalog.listed` lists the `extra` models and `problem` is the line `/model` ends
with; none of them raises.

A table's problems are said with what to do, and a model that can't be used still binds: an
unknown name (the message lists the models and shows an endpoint to add), no provider, an unknown
provider or setting (an endpoint's, or a model's), an `id` on the endpoint itself, no models, a
model with no id, no `base_url` or one that is not an http(s) URL with a host and a numeric port (a
malformed one is that endpoint's problem alone, never the catalog's), a row `extra` that is not one
table per endpoint or a `default` that is not a name, a `key` that is not the name of a line
(capitals, digits and `_`: a value that isn't one may be the key itself, so it is never quoted back)
or that names `CLAUDE_CODE_OAUTH_TOKEN` (below), both `key` and `key_command`, a claude-code
`base_url` without a `key_command` or the other way round, a `max_tokens`, `temperature`,
`key_ttl_ms` or `experimental_betas` of the wrong type (`ModelsError(kind, message)`, CONTRACTS.md:
Errors). An endpoint's problem is any of its models' too, so none of them is used while it has one. Each step
raises it (`Unusable`), so a typo in the models file is a message in the conversation, and
`/model` another model fixes it. `/model NAME` checks first
(`models.check`), so it never switches to one. The models file is read when the model row
starts and each time `models` is asked, never watched: an edit takes effect at the next
`/model` or launch (`/restart model` for the model already chosen).

A provider can also be `module:attribute`, an endpoint whose factory is given each model's table,
its endpoint's with its own over it (its settings are its own). It is there for tests: bh-02's fakes (`bh_02.testing:echo_provider`) are models of
this kind, so a real launch switches between a fake and any other model under this row. It
imports whatever module the models file names, so name only code you trust. A factory that
can't be imported, or raises, is a model that can't be used, like any other (`Unusable`).

**The models file must be outside the project.** It is trusted whole: a factory it names runs
in bh-02's own, unjailed process, a `key_command` it names runs as the person, and a `key` it names
is read from local.env and sent to the table's `base_url`. The project is the working directory, which the jail lets the model's code
write (the python row's root), and the model row's `cwd` too when a layer sets one. A models file in
it would let the model choose both, so it is not read (`providers.known`, `named.in_project`),
however it got there: bh-02 run from the home directory (`~/.config` is then in the project),
`$XDG_CONFIG_HOME` or the row's `models` in the project, or a link into it. It counts as the
project's when the file as named, or any place reading it goes through (each directory and link
on the way, links followed, to where it ends: `host_paths.passes`, the walk the python row's startup
files and memory files outside the project are held to), is under the project's root as named or as
resolved: the model could repoint a link there, or swap a directory there for one, and so choose
what is read. Whether the file is there does not matter (the model could write one). The row's
`extra` still works; the reason is said where the models file's problems
are: `models.problem`, which `/model` shows in place of where to add models, and the error of a
name only that file could have named (`/model NAME`, and each step of a model row whose
`default` is one).

**A key never names the Claude Code token.** Wherever an `openai` table comes from, a `key` of
`CLAUDE_CODE_OAUTH_TOKEN` is that model's problem (`named.withheld`), and the request refuses it
again before it reads local.env (`authorization`): that token is the Claude Code CLI's alone.

`models` (`catalog.py`) reads the model row's config from the loader's entries and the models
file each time it is asked, and depends on the loader and `host` (where a key's `local.env` is
looked for) alone: `/model` (the switch row) and the status bar depend on it, never on `model`,
which a switch replaces.

## /model

`models:switch` (`switch.py`, its row in `wiring.py`) registers `/model` with `commands`, beside
the catalog it reads, so the commands plugin knows nothing of how a model is chosen and a
composition without the catalog keeps the operator's commands. `/model` lists the models (the
`models` value: each endpoint's of the models file, then of the model row's own, each with its
[discovered](#discovering-an-endpoints-models) ones after its named ones, after asking the endpoints:
`models.refresh`), the one the model row names marked `●`, each with its provider and id, the one a
new session starts on when no layer names one marked `(default: the models file)`, and says where the models
file is, or, when it is not read (`models.problem`: it is in the project, or can't be read), why and
where it must be instead. When the models file's `default` is refused (`models.default_problem`: no
name, no model, or a model whose table has a problem) it says so in a line above that, with what to
write, never as an error. The status bar's model comes from `models.current`, which says `unusable`
(the reason) when the row can't use the model it names; the field then reads `NAME (unusable)`, and
`NAME ✗` on a narrow bar, so a name never reads as a model that runs. Its `NAME` is the default's
own text when it is a name, else `default`.
`/model NAME` switches by name, across providers: it asks `models.check(NAME)` first, so a name
that is no model, or a model whose table has a problem, is said and changes nothing; then it
names NAME as the model row's `default` in the session's layer (`layer`, on the row
`model_row`) with cordis's `read_layer`/`format_layer` (`set_model`) and queues a `reload` of
the layers (the watcher would notice too, half a second later), so the choice is composition
and a resumed session keeps it. A NAME the row already names changes nothing; a later layer
that sets the model row's config (a `--patch`, `shadowing`) would replace the session's whole,
so `/model` says so and records nothing. The reload is queued in `jobs` (CONTRACTS.md: jobs),
run after the command has answered, since it restarts the chat row the command's answer is
shown in; one that fails is told through `output.notice` there. The chat row reads its next
line only once the reload is done, so a line typed meanwhile reaches the new model. Its spec
carries `choices`, one per usable model, which the palette offers as entries of their own
(`/model claude/haiku`); they read `models.listed` and never ask a server (below). The row depends on `models`, not on `model`, so a switch reloads the model
row and what uses it, never the row running the switch. The answer ends with `restarting`
(CONTRACTS.md: event), naming the model row, which the ui names in what a line typed meanwhile
says it waits for.

## openai: any OpenAI-compatible endpoint

`openai/` serves any `/chat/completions` endpoint: OpenAI, OpenRouter, Groq, Together, Mistral,
xAI, DeepSeek, Gemini's compatibility endpoint, vLLM, LM Studio, Ollama (`/v1`). Over httpx2
(the one HTTP client, already in the workspace through mcp):
- each step is one streamed POST (`stream: true`, `stream_options.include_usage`), each tool
  offered as a function; `wire.py` (pure) builds it and folds the server-sent events. A server
  that refuses `stream_options` (a 400/422 naming it, as one that forbids fields it doesn't
  know answers) is asked again without it, then and for every later step: usage is optional;
- text and thinking (`reasoning_content`, `reasoning`) stream as they arrive; a call is
  assembled by `index` from its deltas (an id and name first and the arguments in pieces, or
  whole in one delta; without an `index`, as Gemini's endpoint sends them, a new id opens a new
  call, and with neither index nor id, a part naming a function after a whole call does) and
  sent once the stream ends; a call whose arguments don't decode
  carries `error` (the loop's `undecodable`);
- usage from the final usage-only event (`prompt_tokens_details.cached_tokens` as cache reads);
- `stop` is the API's `finish_reason` in the loop's words: `stop`, `length`, `tool_calls`
  (and the legacy `function_call`), `content_filter` as `refusal`;
- `message` is the assistant message in the API's own shape (text or none, calls with their
  arguments as the JSON text sent), replayed as it came; another provider's step (Claude's
  blocks, an old Ollama message) is rebuilt from the transcript's text and calls;
- a stream that ends without a `finish_reason` or `[DONE]` is an error, not a silent stop;
- failures are recoverable and say what to do: 401/403 (`authentication_failed`: the key's
  line of local.env, or that the model names none), 404 (`not_found`: check `base_url` and the
  id), 429 (`rate_limit`), 400 (`invalid_request`), 5xx (`server_error`), an error event
  mid-stream (OpenRouter sends them), a server that isn't there (`connection`: is it running?),
a URL no request can go to (`model_config`); nothing the HTTP client raises escapes as a bug.
  What the server said is quoted with the key the request sent taken out, whole or masked but
  for its end (`sk-proj-****abcd`), as `<key>`: an error is kept in the session's events.

A model's `key` names a line of `local.env`, read when each request is made and put only in
that request's `Authorization` header: never in an environment, never in anything whose repr
shows it. A key named but not there says which file and what line to add, at `/model NAME`
(which looks for the line, never reads it out, and does not switch) and again at a request if
the line is removed since; no key sends none.

A `key_command` instead is a command that prints the key (`key_command.py`): run through the
person's shell, with bh-02's environment and no input, when a request needs a key, its stdout
trimmed. The request's headers are kept for `key_ttl_ms` (5 minutes when unset, Claude Code's own
default for its `apiKeyHelper`) so the command doesn't run every step, and dropped when the server
answers 401 or 403, so the next step runs it again. One that can't start, runs past 60 s, exits
non-zero or prints nothing is an `authentication_failed` naming the command, never what it
printed; so is a key a header can't carry. `/model NAME` doesn't run it to check. Only the models
file may name one: a layer's `extra` that does is that table's problem.
Connecting times out after 10 s; reading does not (a local model can take minutes to its first
token). Closing the step (Ctrl-C) closes the HTTP stream.

## Discovering an endpoint's models

An `openai` endpoint of the models file with `discover = true` also offers the models its server
lists, `ENDPOINT/ID`, beside the ones its `models` names (`named.find`; `openai/listing.py` pure,
`openai/discovery.py` the I/O and the cache), narrowed by an optional `include`, a list of globs
(`fnmatch`: `*`, `?`, `[abc]`, case-sensitive) tried on the id. What is wrong with one is that
table's `problem`, said like any other.

- **Names resolve with no network.** `named.find(name, models)` is the one pure rule: the endpoint of
  that exact name, else `ENDPOINT/MODEL`, split at the first `/` (the rest keeps its
  `/` and `:`), derived from the endpoint's table (`derived`: its provider, `base_url`, key and
  settings, with the table its `models` gives MODEL over them, or MODEL as the id). `chosen`, `check`, `current` and `listed` all go through it, so
  `--model`, `/model NAME`, a layer's `default` and the file's `default` mean the model with no
  request, the status bar shows `local/qwen (openai)`, and the model row has no way to ask a server at
  all: an id the server lacks is the first step's 404. The endpoint alone names no model
  (`not_a_model` says to name one of its models). An endpoint whose table has a problem (an `id`
  on it, a bad `include` or `base_url`) names no model either: `derived` hands back the
  table itself, so `--model local/x`, `/model local/x` and a `default` are refused with that problem
  and what to write, and the model row binds `Unusable` as for any table with one.
- **Only `/model` asks.** `Catalog.refresh()`, awaited by `/model` with no argument in its own
  coroutine, asks each discovering endpoint `GET <base_url>/models` through a `Get` (`openai/discovery.py`: an
  async call returning a `Reply` or a `Down`, never raising for a server that isn't there; `httpx_get`
  is the real one, `testing.FakeGet` the tests'), all at once: connecting within 3 s, the whole
  request within 6 s, no redirect followed (a key goes to its `base_url` alone), at most 1 MiB read
  and held (a chunk that would pass it is not taken).
  It is async I/O, never a call that blocks the loop the TUI shares, and a thread would hold bh-02
  open at exit. `listed` (which `/model`'s `choices` and the composer's completion call, on the
  loop, per key), `endpoints` and `current` (the status bar's) only read what the last `refresh`
  kept, so nothing else ever triggers it (decision-0003).
- **The cache** (`Discovery`, in the catalog row, lost with it) is kept under the endpoint's
  `base_url` and the name of its key's line (or its `key_command`), holding ids and never the key. `refresh` asks an endpoint
  again only when it has no listing, the last one failed, or it is 30 s old: retyping `/model` doesn't
  ask a hosted endpoint again, and typing it once the server is started does at once. A reader never
  expires it (a stale id is a suggestion: resolution never depends on it); a refresh that fails drops
  the ids it had, and one that no longer finds the endpoint in the file forgets it. `include` is
  applied on read, so editing it needs no new request.
- **What `/model` shows.** `listed` gives each endpoint's named models in order, then, sorted, the
  ids its server listed that none of them is, at most 200 (`SHOWN`), as `{name, provider, id,
  current, where}`; the model row's model and the default, when they are `ENDPOINT/ID` names, are
  listed even if the server doesn't list them, so the marks always show. `endpoints()` gives each
  endpoint with a problem or `discover` its `name`, `where` and `notes`, the lines
  `model_list` prints after the models: why it listed none (the server isn't there or took too long,
  HTTP 401/403, no `/models`, a redirect, an answer that isn't a model list, a key's line missing from
  `local.env`, the table's problem), `include` matching nothing, more than 200, entries of its list that give no
  usable id (counted as entries, whether the id is missing or one a name can't be), more than 2000 kept. Never an error, and never the server's text but its ids.
- **Which ids are names** (`listing.usable`): the server's text, so control characters (C0, DEL,
  C1) are stripped, and what remains must be 1 to 200 printable ASCII characters with no space. A
  name is one word in `/model NAME`, and `format_layer` writes a character outside the Basic
  Multilingual Plane as a surrogate-pair escape, which is invalid TOML, so choosing such a name
  would write a session layer the loader can't read. The rest are never listed: a note counts the
  entries of the list that gave no usable id, missing or refused. An
  id is only ever a name and the `model` of a request's body: never a path, an argument or part of a
  URL.
- **Trust.** Discovering endpoints come only from the models file, which is not read when it is in
  the project (above), so the model's code can't add one; a table of a layer's `extra` that says
  `discover` is that table's problem and asks nothing. The key is read from `local.env` (or printed by
  its `key_command`) for the request and goes in its `Authorization` header only (`openai.headers_for`
  over `openai.authorization`, whose
  withheld-token wall applies); a line that is missing, or that holds what a header can't carry
  (anything but printable ASCII), asks nothing and is said, without the key. Whatever a library
  says of a failure goes through `wire.scrubbed` and a control strip first, and a body is never quoted.

## What a step tells the loop about the model

Each `usage` chunk names the model that answered (`model`): claude-code's from `message_start`, openai's
from the response's events (left out when a server names none, or sends no usage). Each provider also
exposes `settings` (CONTRACTS.md: model), which the loop records with a conversation's first step and
whenever it changes: the named model (`ENDPOINT/MODEL`), the provider, and, for openai, the
`max_tokens` and `temperature` it sends (`wire.settings_for`; left out when the model's table sets none).
Claude Code is given neither, so its settings are the model and the provider alone.

## When the tools change mid-conversation

The loop keeps the list a conversation began with in its transcript and tells a change as an
aside ([why](../../../docs/bh-02/how-it-works/prompt-and-asides.md#why-the-prompt-stays-fixed-for-a-conversation)); each provider says which list a request offers (`tool_changes`), and both say
`fixed`, the list the conversation began with, for its life. What each would do with a changed
list:

- **openai**: a chat template renders the tool list at the start of the prompt (llama.cpp,
  Ollama, vLLM, LM Studio), and OpenAI's own prompt cache is a prefix of the request too. A
  changed list would make a local model process the whole conversation again (minutes on a long
  one, looking frozen) and a hosted one bill it uncached. With `fixed` a change costs nothing
  but the aside (it is part of the next message, after the cached prefix); the price is that an
  added tool is not offered natively until the next conversation (`/clear`, `/compact`).
- **claude-code**: Claude Code sends the tools first too. Offering a changed list means
  restarting Claude Code on its session with the new list (what a changed tool set does, above):
  it works, and costs the conversation's cache, as the request's prefix changes at its first
  byte. With `fixed` nothing restarts and the cache holds.

What Claude Code itself would do with a tool-list change, read from the code of the CLI this
plugin pins ([Pinned](#pinned-and-why)) rather than measured (a measurement needs a subscription token, and the
change below cannot be sent today):
- it refreshes an MCP server's tools when the server sends `notifications/tools/list_changed`
  (`Received tools/list_changed notification, refreshing tools`), and refetches them after a
  reconnect;
- tools added or removed mid-conversation are sent as `tool_addition` and `tool_removal` blocks
  in a mid-conversation system message, under the beta `mid-conversation-tool-changes-2026-07-01`
  (with the definitions inline under `inline-tools-2026-09-15`), which keeps the cached prefix;
- if the API rejects that (`[late-tool-additions] tool_addition rejected`), it falls back to
  declaring the tools in `tools[]`, which costs the cache, and stays so until `/clear` or
  `/compact`.

That route is closed to bh-02 for now: the pinned Agent SDK drops what an in-process MCP
server sends on its own (its bridge: "notifications (logging, progress, list_changed) are
dropped"), so bh-02's server cannot tell Claude Code its tools changed. `reconnect_mcp_server`
would make Claude Code list them again, but whether it then adds them as a late addition (cache
kept) or redeclares them (cache lost) is not measured. Until an SDK carries the notification,
`fixed` is the cheapest route that works.

## claude-code: Claude through Claude Code

Claude, with a subscription token or through a company gateway, as the model under bh-02's own
`agent:loop`. The model is reached through the Claude Agent SDK, which is Claude Code: the
subscription's sanctioned route. bh-02 never imitates Claude Code's requests by hand. The shape is pi's
(`pi-claude-agent-sdk`, `pi-claude-bridge`): Claude Code carries the model's steps, and bh-02
runs the loop. It is `claude_code/` (`ClaudeCodeModel`, `ClaudeCodeConfig`): `model` is
the named model's id, `state` the session's own directory (which the session layer sets on the
model row), `env_file` where the credential is, `cwd` the project directory.

Why this shape, and not the two bh-02 ran before: Claude Code's own loop (the first of them) would
own the conversation, the approvals and the tool, and the plain Messages API with the
subscription token (the second) answered only on Haiku, since the subscription reaches every
model only through Claude Code. As a `model` under the loop, the same shape as the `openai`
provider, every model step reaches the loop as one step, so approval is in one place for every
provider, and nothing about the loop depends on which one runs.

Failures are `ClaudeCodeError(kind, message)` (CONTRACTS.md: Errors). The kinds are
Claude Code's own (`authentication_failed`, `rate_limit`, `billing_error`, `invalid_request`,
`server_error`, `unknown`), `result_error` (Claude Code ended the query before the step), `connection`,
`strayed` (Claude Code answered a call itself twice in a row) and `path_too_long` (a rebuild
that can't name Claude Code's session directory); the sections below say when each happens.

### Who does what

bh-02's loop does all of the following:
- classifies each step (`stops.classify`) and nudges;
- runs every call through its tool (python's as an input in the Python process), asking the person first when the runner does not confine it;
- keeps the transcript.

Claude Code does none of that. It runs with no built-in tool (`tools=[]`), no settings file
or CLAUDE.md (`setting_sources=[]`), and no connector (`strict_mcp_config`,
`ENABLE_CLAUDEAI_MCP_SERVERS=0`). Through a gateway it is given one settings layer, bh-02's own
(below), and still reads none of the person's. Its system prompt is the request's system message, after a
line of the provider's own: Claude Code names the declared tool `mcp__bh__python`, so the line
says that is bh-02's `python`. It does not compact (`DISABLE_AUTO_COMPACT`).

**The tools are only declared.** The loop's tools (the shipped composition's: `python`) reach
Claude Code as an in-process MCP server (`declared.py`, the MCP library's low-level `Server`),
so the model calls `mcp__bh__python` through standard tool calling. Claude Code calls the
server, and the call *parks* there. The server runs nothing: the loop runs the call, and the
next request brings the result, which the parked call returns. `can_use_tool` denies anything
but a declared tool (`mcp__bh__<name>`) without asking. That is a second wall: nothing else is offered anyway.

### One step per `complete`

One Claude Code process holds a conversation. It starts on the first step and uses one
`ClaudeSDKClient`. How each step goes:
- **A new user line** starts a query.
- **A step that asks for tools** ends at its `message_stop`, and the query stays open. The
  results the loop sends next are handed to the parked calls, paired by the tool_use id that
  Claude Code puts in the MCP request's `_meta` (`claudecode/toolUseId`). A result that comes
  before its call waits for it.
- **A line the person typed after stopping a reply mid-call** is pushed at priority `next`,
  before the results.
- **An answered step** (`end_turn` with text) is read to the query's result.
- **Any other end** is interrupted at once: the output limit, a silent step, a refusal, or a
  call that did not decode. The loop's classification and nudges then decide. Claude Code has
  recoveries of its own for most of these (it continues a truncated step, retries a silent
  one): left alone, it continued a truncated step three times and then failed (measured).
- **Closing the step** interrupts Claude Code and reads it to its result. This is Ctrl-C:
  chat cancels the reply's task and the loop closes this generator. Closed on the step's last
  chunks (the final `usage`, which the loop is still showing), an answered or cut step has
  already settled: nothing is interrupted, and the loop's `[stopped]` entry continues the same
  process. A tool step closed there is interrupted and drained at once (the loop won't answer
  its calls), saved as failed, and the next request rebuilds.
- **Stopping the process** with calls parked (a rebuild, or leaving) interrupts Claude Code
  first and only then answers the calls `closed`, so it can't start another model request on
  that answer (measured: closing took about 4 s the other way round, under 0.5 s this way).

`stream.py` folds each step's raw Messages API stream events (`StreamEvent.event`) into chunks:
- text and thinking arrive as they stream;
- a tool call arrives once its block ends, under the loop's name for it (`python`, not
  `mcp__bh__python`); one whose arguments did not decode (or never began) waits, with
  whatever follows it, for the step's stop reason, and only then arrives with its `error`.
  Claude Code closes a stream it will retry with the open block's end and no stop reason
  (measured), so a call that connection cut off is never shown;
- two usage parts, the first `partial`;
- the API's own stop reason, so `stops.classify` works unchanged: `end_turn`, `tool_use`,
  `max_tokens`, `stop_sequence`, `refusal` and `model_context_window_exceeded` (truncated, like
  `max_tokens`). `pause_turn` comes only for a request with server tools, which bh-02 never
  sends, so the loop has no case for it. A call's arguments stream as JSON, so a call can be
  undecodable;
- the assistant message as received, for replay.

On `haiku`, Claude Code sends each thinking block with its text empty and only the signature
(measured; Sonnet and Opus steps had no thinking blocks). Such a step shows no thinking, but its
output tokens and cost include it, so a one-line answer can read as a couple of hundred tokens
out. The signed block is kept verbatim for replay.

Cost is what the step would cost on the API, from a price table; the subscription itself bills
nothing per token.

### What Claude Code holds, and rebuilds

`reconcile.py` (pure) checks every request against what Claude Code's session holds. That is
the first `count` transcript messages, plus the step it emitted last. Some divergences are
accepted in place, each measured to leave the session equivalent with the cache warm:
- the loop's entry for that step;
- a cut step's provider-less entry, matched by its text;
- a stopped step's `[stopped]` entry;
- results for exactly the open calls.

Anything else is a **rebuild**: a `/clear`, a failed step, a call Claude Code answered itself,
or results that are not the open calls'. A call Claude Code answers itself (an undeclared one,
which the permission callback denies) lets it start the next step on its own answer before the
loop's results arrive; that step is dropped unseen and the rebuild happens in the same request,
so the loop never streams a step the model built on a result the loop did not send. A tool step
the person stops on its last chunks is interrupted at once (the loop won't answer its calls),
and the next request rebuilds. `records.py` writes the transcript as a new Claude Code
session file, and a new process resumes it:
- the file is a linear `parentUuid` chain;
- `provider` blocks go in verbatim, thinking signatures included;
- a tool name is kept as Claude Code sent it (`mcp__bh__python`), and the calls of a step with no
  `provider` message (another provider's, rebuilt from its text and calls) get `mcp__bh__`;
- every record carries the resolved model id, since with an alias Claude Code re-cached the
  whole conversation (measured);
- each rebuild gets a new session id.

A working directory whose path, slugged, is longer than 200 characters gets a hashed directory
name of Claude Code's own, which bh-02 can only find once Claude Code has made it. When it can't
be named, the step fails with `path_too_long` and says to run from a shorter path or /clear,
rather than start a fresh session that has lost the conversation.

A transcript that ends in tool results, not a user line, is continued with a one-line message
(`CONTINUE`).

A changed system prompt or tool set restarts the process on its own session before the next user
line, never while calls are parked. `agent:loop` sends a conversation the prompt and the tools
it began with and tells later changes (the branch, an extension, a tool added) as asides, and the
date with the person's message (its `today` field is the loop's own: both providers send a user
entry's `content` alone), so within a conversation neither changes and the process is restarted
only for a new conversation (`/clear`, `/compact`).

### State, per session

`state` is `<session dir>/claude`. It holds:
- `config/`: Claude Code's `CLAUDE_CONFIG_DIR`, isolated from `~/.claude` (and ~170 tokens per
  request cheaper);
- `state.json`: the session id, what it holds, and how its last step ended;
- `stderr.log`: the CLI's stderr, because the TUI owns the terminal.

`bh-02 --resume` continues Claude Code's own session when the transcript still matches. A crash
with calls parked or a step streaming reads as failed, and the session is rebuilt. A call the crash
left without a result is answered by `agent:loop` before the first request (`interrupted: ...`,
CONTRACTS.md: call record), so the rebuilt session holds a result for every call it asked for.
Without `state`, a temporary directory is used and removed.

### The credential

These are the credential's rules; every other page that mentions them points here.

The credential is `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token` makes one), one line of the
git-ignored `local.env` at the repository root (mode 600), so `uv run bh-02` needs no
`--env-file`.
- **Who reads it: the model rows, from the file.** Where it is looked for is not this plugin's
  to decide: both rows depend on `host`, and its `credentials` (above bh-02's install and its
  environment, nearest first: `bh_02.cli.credential_search`, the one definition of that search)
  are the places searched; `token_file` takes the first that is a regular file (the row's
  `env_file` instead, when set), so the empty directory a Linux jail holds an absent one with
  never hides the real file, at the first read or at any later one (each Claude Code start, each
  openai request). `parse_env` (pure) reads it with one read.
- **Where it goes: only to the Claude Code CLI.** The token goes only into the SDK options' `env`
  for the Claude Code child: never into bh-02's `os.environ`, so no program the runner starts
  can inherit it; never on a command line; never in a repr (the child's env is a `ChildEnv`,
  whose repr names its keys only, since Textual prints a crash with every frame's locals). The
  child starts detached, with every other `ANTHROPIC_*` and `CLAUDE_*` removed (below).
- **Never `ANTHROPIC_API_KEY`.** bh-02 never sets or reads `ANTHROPIC_API_KEY` or
  `ANTHROPIC_AUTH_TOKEN`, and the token is never printed, logged or committed. No model's `key`
  may name it (above).
- **The model's code never gets it.** The same list is among the jail's `secrets`, so no place
  searched is one a jailed input can read, write or create; `runner:unconfined` (`--no-jail`)
  starts every program without `CLAUDE*` or `ANTHROPIC_*`, and `!COMMAND` runs without them too
  (the commands plugin's README). An input approved under `--no-jail` runs with the person's
  permissions, so it could still open `local.env` itself: the
  [runner plugin's README](../runner-cordis-plugin/README.md) has the jail's policy, and how
  `/release` lets the person add a credential mid-session.
- **Without it** the row still binds, and each step answers `authentication_failed`, naming the
  file it read (the row's `env_file` when set), whether that file is missing or lacks the
  variable, and to make a token with `claude setup-token`.

### Through a gateway

A `claude-code` endpoint with `base_url` and `key_command` sends Claude Code's requests to that
Anthropic-compatible gateway instead, with the key the command prints: a company's own route to
Claude, where there is no subscription token. The provider (`ClaudeCodeConfig.gateway`, a
`credential.Gateway`) starts the CLI with the SDK's `settings` set to a layer of bh-02's own,
inline JSON (`credential.gateway_settings`: `apiKeyHelper` is the command, `env` sets
`ANTHROPIC_BASE_URL`, `CLAUDE_CODE_API_KEY_HELPER_TTL_MS` from `key_ttl_ms`, and
`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` for `experimental_betas = false`), still with
`setting_sources=[]`, so the person's own settings stay out. Measured on a gateway, with the pinned
CLI: the flag layer is applied though no setting source is, the CLI runs the helper itself, and a
`[1m]` id works. A helper's key the gateway refuses is `authentication_failed` naming the gateway and
the command (`failure_of`); the CLI retries it for about three minutes first (measured).
- **No token.** The child's environment is `credential.gateway_env`: the fixed settings,
  `CLAUDE_CONFIG_DIR`, and `CLAUDE_CODE_OAUTH_TOKEN` set empty, so a token in bh-02's own
  environment never reaches it (the SDK merges that environment under the options' `env`). `local.env`
  is not read.
- **bh-02 never holds the key.** The CLI runs the command; bh-02 only names it. The base URL goes in
  the settings layer, not the environment, so the detached launcher's scrub of `ANTHROPIC_*` (below)
  stays as it is.

### Detached: its own process group, with the Anthropic and Claude variables dropped

The SDK starts the CLI through this plugin's `claude-code-detached` console script
(`detach.py`). The script calls `setsid`, because a terminal's Ctrl-C signals the whole process
group and the CLI exits on SIGINT: in a session of its own, the terminal's SIGINT never reaches
it, and a stop is the loop closing its step. It then `execve`s the SDK's bundled CLI with every
`ANTHROPIC_*` and `CLAUDE_*` variable removed but the ones the SDK and the options set (the
credential variable, which is the subscription token or empty through a gateway,
`CLAUDE_CONFIG_DIR`, the SDK's entry point and version). A gateway's base URL is not among
them: it reaches the CLI in its settings layer (above). The SDK merges bh-02's
environment into the child's, and its options can override a key but not remove one; without
the scrub, a shell's `CLAUDE_CODE_USE_BEDROCK=1` sent the steps to Bedrock (measured: the
start timed out), and `CLAUDE_CODE_MAX_OUTPUT_TOKENS` and the like would change the steps.

### Pinned, and why

`claude-agent-sdk==0.2.158` (bundled CLI 2.1.280) is pinned, because the design leans on Claude
Code internals that a CLI upgrade can break without a type error:
- `claudecode/toolUseId` in the MCP call's `_meta`;
- the `next` priority's ordering;
- the session file format;
- the tool `_meta` keys `anthropic/maxResultSizeChars` and `anthropic/alwaysLoad`. Without both
  of these and `MAX_MCP_OUTPUT_TOKENS`, a large result was replaced by a file the model could not
  read (measured).

Bump the pin deliberately, and run the e2e tests.

## Tests

- `test_named_models.py`, `test_openai_wire.py` and `test_claude_code_{credential,stream,reconcile,records}.py` are pure.
- `test_models_file_trust.py`, on files and links in temporary directories: a models file in
  the project as named, through `$XDG_CONFIG_HOME`, from the home directory, a link to one in
  it, a directory on its path linked into it and a link in it on the way out are not read (the
  `extra` still is, and the catalog, `/model NAME` and the step say why); one
  outside is read; a key naming the Claude Code token is refused and nothing reaches the server.
- `test_models_key_command.py`: a `key_command`'s key, what a failing one says (never what it
  printed), the openai provider keeping its headers for `key_ttl_ms` and dropping a refused key
  (against `StubServer`), discovery asking with it, and `extra` refusing it.
- `test_models_gateway.py`: the gateway's settings layer and token-less environment, the provider
  starting `FakeClaudeCode` with both and no `local.env`, and what a refused key says.
- `test_models_wiring.py` drives the rows by hand: the named model's provider, entered; a
  model that can't be used, binding anyway; a factory provider; the catalog.
- `test_openai_stub.py` runs the openai provider against `openai.testing.StubServer`, a
  stand-in OpenAI-compatible server on a real socket streaming real server-sent events:
  streamed text, a python call's round trip, a call that doesn't decode, the key from
  local.env (and never in `os.environ`), error statuses and one mid-stream, a wrong `base_url`
  and a server that isn't there, and a stopped step whose connection the server sees closed.
- `test_claude_code_model.py` drives Claude Code's provider over `claude_code.testing.FakeClaudeCode`. The
  fake speaks the SDK's own message types, and calls the declared tools over the MCP protocol
  itself (an `mcp.Client` on the options' server) with the tool_use id in `_meta`.
- `test_claude_code_live.py` (`e2e`, opt-in) runs against the real CLI on Sonnet: one answer,
  then a tool round trip recalled from Claude Code's own session and from a rebuilt one. Run it
  with `uv run pytest bh-02/plugins/models-cordis-plugin -m e2e -q`.
