# models-cordis-plugin

bh-02's model: named models over their providers, switched by name. Three rows:

| Row | Binds / registers | Consumes |
|---|---|---|
| `models:model` | `model`: one model step per `complete(messages, tools)` (CONTRACTS.md: model), the model `default` names on its provider | `layers` (`credentials`: where `local.env` is looked for) |
| `models:catalog` | `models`: the models there are, the one the model row names now, why a name can't be switched to, and why the models file is not read (CONTRACTS.md: models) | `loader`, `layers` |
| `models:switch` | registers `/model [NAME]`: lists the models, switches by name in the session's layer, the reload queued in `jobs`; config: `layer` (the session's), `model_row` (`model`) | `commands` (`register`), `loader`, `models`, `jobs` (`put`) |

The model row's config (`ModelConfig`):
- `default`: the model's name, `sonnet` unless a layer says another; `--model` and `/model` set it.
- `models`: the models file, when not the default one.
- `extra`: models of the row's own, one table per name as in the file (a migrated layer
  writes one: an old Ollama row is an `extra` OpenAI-compatible model).
- `state`, `env_file`, `cwd`: the claude-code provider's (below). `env_file` is also where the
  openai provider reads a model's key. Unset, `local.env` is looked for where the `layers`
  value's `credentials` say (below). A models file must be outside `cwd` as well as the
  working directory (below).

## Named models

Three places name models, each over the last (`named.py`, pure but for reading the file):
- the built-ins: `sonnet`, `opus` and `haiku`, Claude through Claude Code by its aliases;
- the models file, `$XDG_CONFIG_HOME/bh-02/models.toml` (else `~/.config/bh-02/models.toml`);
- the row's `extra`.

A later one of the same name wins: `extra` over the file, and a user's model over a built-in
(allowed, and `/model` notes it as shadowing the built-in). The file is one table per model:

```toml
[llama]                                   # Ollama is an OpenAI-compatible endpoint at /v1
provider = "openai"
id = "llama3.2"
base_url = "http://localhost:11434/v1"

[router]
provider = "openai"
id = "anthropic/claude-sonnet-4"
base_url = "https://openrouter.ai/api/v1"
key = "OPENROUTER_API_KEY"                # a line of local.env, never the key itself
max_tokens = 4096                         # optional, sent only when set
temperature = 0.2                         # optional, sent only when set

[opus-4-1]
provider = "claude-code"
id = "claude-opus-4-1"
```

A table's problems are said with what to do, and a model that can't be used still binds: an
unknown name (the message lists the models and shows a table to add), no provider, an unknown
provider or setting, no id, no `base_url` or one that is not an http(s) URL with a host and a
numeric port (a malformed one is that model's problem alone, never the catalog's), a row
`extra` that is not one table per model or a `default` that is not a name, a `key` that is not the
name of a line (capitals, digits and `_`: a value that isn't one may be the key itself, so it
is never quoted back) or that names `CLAUDE_CODE_OAUTH_TOKEN` (below), a `max_tokens` or
`temperature` of the wrong type (`ModelsError(kind, message)`, CONTRACTS.md: Errors). Each step
raises it (`Unusable`), so a typo in the models file is a message in the conversation, and
`/model` another model fixes it. `/model NAME` checks first
(`models.check`), so it never switches to one. The models file is read when the model row
starts and each time `models` is asked, never watched: an edit takes effect at the next
`/model` or launch (`/restart model` for the model already chosen).

A provider can also be `module:attribute`, a factory given the model's table (its settings are
its own). It is there for tests: bh-02's fakes (`bh_02.testing:echo_provider`) are models of
this kind, so a real launch switches between a fake and any other model under this row. It
imports whatever module the models file names, so name only code you trust. A factory that
can't be imported, or raises, is a model that can't be used, like any other (`Unusable`).

**The models file must be outside the project.** It is trusted whole: a factory it names runs
in bh-02's own, unjailed process, and a `key` it names is read from local.env and sent to the
table's `base_url`. The project is the working directory, which the jail lets the model's code
write (the kernel's root), and the model row's `cwd` too when a layer sets one. A models file in
it would let the model choose both, so it is not read (`providers.refused`, `named.in_project`),
however it got there: bh-02 run from the home directory (`~/.config` is then in the project),
`$XDG_CONFIG_HOME` or the row's `models` in the project, or a link into it. It counts as the
project's when the file as named, or any place reading it goes through (each directory and link
on the way, links followed, to where it ends: `host_paths.passes`, the walk the kernel's startup
files and memory files outside the project are held to), is under the project's root as named or as
resolved: the model could repoint a link there, or swap a directory there for one, and so choose
what is read. Whether the file is there does not matter (the model could write one). The
built-ins and the row's `extra` still work; the reason is said where the models file's problems
are: `models.problem`, which `/model` shows in place of where to add models, and the error of a
name only that file could have named (`/model NAME`, and each step of a model row whose
`default` is one).

**A key never names the Claude Code token.** Wherever an `openai` table comes from, a `key` of
`CLAUDE_CODE_OAUTH_TOKEN` is that model's problem (`named.withheld`), and the request refuses it
again before it reads local.env (`authorization`): that token is the Claude Code CLI's alone.

`models` (`catalog.py`) reads the model row's config from the loader's entries and the models
file each time it is asked, and depends on the loader and `layers` (where a key's `local.env` is
looked for) alone: `/model` (the switch row) and the status bar depend on it, never on `model`,
which a switch replaces.

## /model

`models:switch` (`switch.py`, its row in `wiring.py`) registers `/model` with `commands`, beside
the catalog it reads, so the commands plugin knows nothing of how a model is chosen and a
composition without the catalog keeps the operator's commands. `/model` lists the models (the
`models` value: the built-ins, the models file's, the model row's own), the one the model row
names marked `●`, each with its provider and id, and says where the models file is, or, when it
is in the project and so not read (`models.problem`), why and where it must be instead.
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
(`/model haiku`). The row depends on `models`, not on `model`, so a switch reloads the model
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
  arguments as the JSON text sent), replayed as it came; another provider's turn (Claude's
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
Connecting times out after 10 s; reading does not (a local model can take minutes to its first
token). Closing the step (Ctrl-C) closes the HTTP stream.

## When the tools change mid-conversation

A request sends the tool list before anything else, so a list that changes partway through a
conversation makes the whole conversation new to a model server's cache. The loop keeps the
list a conversation began with in its transcript and tells a change as a note (CONTRACTS.md:
tools); each provider says which list a request offers (`tool_changes`), and both say `fixed`,
the list the conversation began with, for its life.

- **openai**: a chat template renders the tool list at the start of the prompt (llama.cpp,
  Ollama, vLLM, LM Studio), and OpenAI's own prompt cache is a prefix of the request too. A
  changed list would make a local model process the whole conversation again (minutes on a long
  one, looking frozen) and a hosted one bill it uncached. With `fixed` a change costs nothing
  but the note (it is part of the next message, after the cached prefix); the price is that an
  added tool is not offered natively until the next conversation (`/clear`, `/compact`).
- **claude-code**: Claude Code sends the tools first too. Offering a changed list means
  restarting Claude Code on its session with the new list (what a changed tool set does, above):
  it works, and costs the conversation's cache, as the request's prefix changes at its first
  byte. With `fixed` nothing restarts and the cache holds.

What Claude Code itself would do with a tool-list change, read from the code of the CLI this
plugin pins (2.1.280) rather than measured (a measurement needs a subscription token, and the
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

That route is closed to bh-02 for now: the Agent SDK (0.2.158) drops what an in-process MCP
server sends on its own (its bridge: "notifications (logging, progress, list_changed) are
dropped"), so bh-02's server cannot tell Claude Code its tools changed. `reconnect_mcp_server`
would make Claude Code list them again, but whether it then adds them as a late addition (cache
kept) or redeclares them (cache lost) is not measured. Until an SDK carries the notification,
`fixed` is the cheapest route that works.

## claude-code: Claude through Claude Code

Claude, on a Claude subscription, as the model under bh-02's own `agent:loop`. The model is
reached through the Claude Agent SDK, which is Claude Code: the subscription's sanctioned
route. bh-02 never imitates Claude Code's requests by hand. The shape is pi's
(`pi-claude-agent-sdk`, `pi-claude-bridge`): Claude Code carries the model's steps, and bh-02
runs the loop. It is `claude_code/` (`ClaudeCodeModel`, `ClaudeCodeConfig`): `model` is
the named model's id, `state` the session's own directory (which the session layer sets on the
model row), `env_file` where the credential is, `cwd` the project directory.

Failures are `ClaudeCodeError(kind, message)` (CONTRACTS.md: Errors). The kinds are
Claude Code's own (`authentication_failed`, `rate_limit`, `billing_error`, `invalid_request`,
`server_error`, `unknown`), `result_error` (Claude Code ended the query before the step), `connection`,
`strayed` (Claude Code answered a call itself twice in a row) and `path_too_long` (a rebuild
that can't name Claude Code's session directory); the sections below say when each happens.

### Who does what

bh-02's loop does all of the following:
- classifies each step (`stops.classify`) and nudges;
- runs every call as an input in the kernel, asking the person first when the kernel is unjailed;
- keeps the transcript.

Claude Code does none of that. It runs with no built-in tool (`tools=[]`), no settings file
or CLAUDE.md (`setting_sources=[]`), and no connector (`strict_mcp_config`,
`ENABLE_CLAUDEAI_MCP_SERVERS=0`). Its system prompt is the request's system message, after a
note of the provider's own: Claude Code names the declared tool `mcp__bh__python`, so the note
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
  call that did not decode. The loop's classification and nudges then decide. Left alone,
  Claude Code's own recovery continued a truncated step three times and then failed
  (measured).
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
  (CLI 2.1.282), so a call that connection cut off is never shown;
- two usage parts, the first `partial`;
- the API's own stop reason, so `stops.classify` works unchanged;
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
- tool names get `mcp__bh__`, so an older session that ran on the Messages API rebuilds too;
- every record carries the resolved model id, since with an alias Claude Code re-cached the
  whole conversation (measured);
- each rebuild gets a new session id.

A working directory whose path, slugged, is longer than 200 characters gets a hashed directory
name of Claude Code's own, which bh-02 can only find once Claude Code has made it. When it can't
be named, the step fails with `path_too_long` and says to run from a shorter path or /clear,
rather than start a fresh session that has lost the conversation.

A transcript that ends in tool results, not a user line, is continued with a one-line note
(`CONTINUE`).

A changed system prompt or tool set restarts the process on its own session before the next user
line, never while calls are parked. `agent:loop` sends a conversation the prompt and the tools
it began with and tells later changes (the branch, an extension, a tool added) as notes, and the
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
with calls parked or a step streaming reads as failed, and the session is rebuilt. Without
`state`, a temporary directory is used and removed.

### The credential

The credential is `CLAUDE_CODE_OAUTH_TOKEN` (`claude setup-token` makes one), kept in the
git-ignored `local.env` at the repository root. Where it is looked for is not this plugin's to
decide: both rows depend on `layers`, and its `credentials` (above bh-02's install and its
environment, nearest first, from `bh_02.cli`) are the places searched; `token_file` takes the
first that is a regular file, so the empty directory a Linux jail holds an absent one with never
hides the real file, at the first read or at any later one (each Claude Code start, each
openai request). The same list is among the jail's `secrets`, so no place searched is one a
jailed input can read, write or create. `parse_env` (pure) reads it with one read, and the
token goes only into the SDK options' `env` for the Claude Code child:
- never into bh-02's `os.environ`, so the kernel and the jail can't inherit it;
- never on a command line.

The child's env is a `ChildEnv`, whose repr names its keys only (Textual prints a crash with
every frame's locals). Without a token, the row still binds, and each step answers
`authentication_failed`, naming the file it read (the row's `env_file` when set), whether that
file is missing or lacks the variable, and to make a token with `claude setup-token`.

### Detached, and on the subscription only

The SDK starts the CLI through this plugin's `claude-code-detached` console script
(`detach.py`). The script calls `setsid`, because a terminal's Ctrl-C signals the whole process
group and the CLI exits on SIGINT. It then `execve`s the SDK's bundled CLI with every
`ANTHROPIC_*` and `CLAUDE_*` variable removed but the ones the SDK and the options set (the
token, `CLAUDE_CONFIG_DIR`, the SDK's entry point and version). The SDK merges bh-02's
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
  built-ins and `extra` still are, and the catalog, `/model NAME` and the step say why); one
  outside is read; a key naming the Claude Code token is refused and nothing reaches the server.
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
