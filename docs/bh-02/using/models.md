# Models

bh-02 runs one model at a time, chosen by name. It has no models built in: every model is one
you name in your models file ([below](#adding-your-own-the-models-file)), and the file's `default`
is the one a new session starts on. You can start on another, and switch mid-session.

## Claude on your subscription

```toml
default = "claude/sonnet"

[claude]
provider = "claude-code"
models = { sonnet = { id = "sonnet" }, opus = { id = "opus" }, haiku = { id = "haiku" } }
```

`claude/sonnet`, `claude/opus` and `claude/haiku` are Claude through Claude Code on your
subscription, by Claude Code's own aliases; they need the credential in `local.env`
([Get started](../get-started.md#the-credential)). Any other Claude model goes in the same way, by
its id (`opus41 = { id = "claude-opus-4-1" }`).

## Choosing a model

- **At launch**: `bh-02 --model claude/opus`.
- **When resuming**: `bh-02 --resume --model claude/haiku` carries the session on with another model.
- **Mid-session**: `/model` lists the models, with the current one marked `●`, the default one marked
  `(default: the models file)`, each one's provider and id, and where your models file is. It also asks each
  endpoint you set to list its models ([below](#listing-an-endpoints-models-discover)). `/model NAME` switches to one. The
  conversation carries on: the transcript is a row of its own, and only the model row and what
  depends on it reload.

When you give neither, bh-02 starts on the model your models file names as the default
([below](#choosing-the-default)). With no default either, no model is chosen: bh-02 starts, the
status bar says `model: none (unusable)`, and your first message answers with what to write.

A switch is written into the session's own layer, so a resumed session keeps the model you last
chose. The status bar shows the model and its provider, `model: claude/sonnet (claude-code)`, and
`starting…` while a new one comes up; a model that can't be used shows `(unusable)` instead of
looking like one that runs.

## Choosing the default

Put `default = "NAME"` at the top of the models file, above the first table, to start new
sessions on one of your models without a flag:

```toml
default = "local/qwen"

[local]
provider = "openai"
base_url = "http://localhost:11434/v1"

[local.models.qwen]
id = "qwen3-coder"
```

A new session takes the default when it starts and records it in its own layer, as `--model`
does, so it keeps that model when you resume it, whatever the file says later; change the file
and only new sessions move. What a new session starts on, strongest first: `--model`, then the
models file's `default`. `/model` still switches mid-session.

The default must be a model's name. A default bh-02 can't use never quietly becomes another
model, since the default chooses what you spend: the session starts, the model row says what to
write at your first message (a default that is not a name, a number say, or names no model: `no
model named 'gone', the default in the models file ...`), the status bar says `model: default
(unusable)` or `gone (unusable)`, and `/model` lists the models and a line saying the default is
refused and why. `/model NAME` of a model that works switches, and so does `--model`; such a
session is listed by `bh-02 sessions` as started on `default`. Like the models themselves, the
default is read only from the models file in your config directory, never from one in the
project.

If the models file itself can't be read (not TOML, a key that is no table, a path that is no
file), it offers no models: the first message says what is wrong with the file, and `/model` ends
with that problem in place of where to add models. Models a layer's `extra` names (a `--patch`)
still work.

## Adding your own: the models file

Your models go in `~/.config/bh-02/models.toml` (`$XDG_CONFIG_HOME/bh-02/models.toml` when that
variable is set). Each table is an **endpoint**: a server and how to reach it. Its models go under
it, in its `models`, and each is named `ENDPOINT/MODEL` in bh-02. Every provider is written the same
way.

```toml
[local]
provider = "openai"
base_url = "http://localhost:11434/v1"

[local.models.qwen]
id = "qwen3-coder"

[router]
provider = "openai"
base_url = "https://openrouter.ai/api/v1"
key = "OPENROUTER_API_KEY"
max_tokens = 4096

[router.models.sonnet]
id = "anthropic/claude-sonnet-4"
temperature = 0.2
```

Then `/model local/qwen`, or `bh-02 --model router/sonnet`.

`[local.models.qwen]` is TOML for a table `qwen` in the table `models` in `[local]`, so the same
models can be written inline, which reads better for a list of them:

```toml
[local]
provider = "openai"
base_url = "http://localhost:11434/v1"
models = { qwen = { id = "qwen3-coder" }, llama = { id = "llama3.2" } }
```

A model's settings are its endpoint's, with its own over them: `router/sonnet` above is sent with
the endpoint's `max_tokens` and its own `temperature`.

| Setting | Where | What it is |
|---|---|---|
| `provider` | endpoint | `claude-code` (Claude through Claude Code) or `openai` (any OpenAI-compatible `/chat/completions` endpoint) |
| `base_url` | endpoint | `openai`: the endpoint, ending before `/chat/completions`. `claude-code`, optional: a gateway ([below](#claude-through-a-gateway)) |
| `key` | endpoint | `openai` only, optional: the **name** of a line in `local.env` that holds the API key |
| `key_command`, `key_ttl_ms` | endpoint | optional: a command that prints the key, and how long a key it printed is used ([below](#the-key)) |
| `experimental_betas` | endpoint | `claude-code` through a gateway, optional: `false` when the gateway refuses Anthropic's beta headers |
| `models` | endpoint | its models, one table each, named `ENDPOINT/MODEL` |
| `discover`, `include` | endpoint | `openai` only, optional: `discover = true` also offers the models its server lists, `include` narrows them ([below](#listing-an-endpoints-models-discover)) |
| `id` | model | the model's id at that provider |
| `max_tokens`, `temperature` | either | `openai` only, optional: sent with each request when set; a model's own win over its endpoint's |

The `openai` provider works with OpenAI, OpenRouter, Groq, Together, Mistral, xAI, DeepSeek,
Gemini's compatibility endpoint, vLLM, LM Studio and Ollama (at `/v1`). A `claude-code` endpoint
without a `base_url` reaches other Claude models on your subscription by their ids.

`ENDPOINT/ID`, where `ID` is not one of the endpoint's `models`, means that id on the endpoint:
`/model router/meta-llama/llama-4` works without a table for it. The name is split at the first `/`,
so an id may hold more of them, and `:`.

A table with an `id` of its own is from before endpoints: bh-02 refuses it and shows how to move the
id under the table's `models`. An endpoint's name may not hold `/`.

### Claude through a gateway

Where Claude is reached through a company's Anthropic-compatible gateway rather than a claude.ai
subscription, give a `claude-code` endpoint the gateway's `base_url` and a `key_command` that
prints its key:

```toml
default = "work/opus"

[work]
provider = "claude-code"
base_url = "https://gateway.example.com/anthropic"
key_command = "my-token-helper get_token"
experimental_betas = false

[work.models.opus]
id = "claude-opus-5-5"

[work.models.sonnet]
id = "claude-sonnet-5-5"
```

These are what Claude Code's own settings call `ANTHROPIC_BASE_URL` and `apiKeyHelper`. bh-02
hands them to the Claude Code CLI it starts, as a settings layer of its own; the CLI runs the
command and runs it again when its key is `key_ttl_ms` old (Claude Code's own default when unset).
bh-02 itself never runs it or holds the key, and needs no `CLAUDE_CODE_OAUTH_TOKEN`. Nothing else
of your Claude Code settings is read. `base_url` and `key_command` come together: one without the
other is refused. A `claude-code` endpoint without them still uses the subscription.

### Listing an endpoint's models: discover

A server you run yourself may serve many models, and a table each is a chore. Give the
endpoint `discover = true` instead, beside or in place of its `models`:

```toml
default = "local/qwen2.5-coder:7b"

[local]
provider = "openai"
discover = true
base_url = "http://localhost:11434/v1"
include = ["qwen*", "llama3*"]    # optional: only the ids matching one of these globs
```

`/model` then asks the server which models it has (`GET <base_url>/models`) and lists each as
`local/ID`, after the endpoint's own `models`: `local/qwen2.5-coder:7b`, `local/llama3.2:latest`.
The name is the table's name, a `/`, and the server's id, split at the first `/`, so an id may
hold more of them (`local/Qwen/Qwen2.5-Coder`) and `:`. An id one of its `models` already is,
is not listed twice. `/model local/qwen2.5-coder:7b`, `bh-02 --model local/qwen2.5-coder:7b`, a layer's
`default` and the models file's `default` all take such a name, and none of them asks the server:
`local/ID` means the model `ID` on that endpoint, whether or not the server lists it, so bh-02 starts
and switches with the server down. An id the server doesn't have is that first message's 404.

What to know:
- The endpoint is not a model itself: it takes no `id`, and `--model local` says to name one of its
  models. Its models share its `key`, `max_tokens` and `temperature`. An endpoint with something
  wrong in it (an `id`, a bad `include` or `base_url`) names no models: `local/ID` is refused, as a
  model of any endpoint with a problem is, with that table's problem and what to write.
- `include` is a list of globs (`*`, `?`, `[abc]`), case-sensitive, tried on the id as the server
  says it (`qwen*`, not `local/qwen*`); a model is listed if any matches. Use it for a server that
  lists hundreds: `/model` shows 200 of an endpoint's models and says how many it left out.
- Only `/model` asks the server, and it waits at most 6 seconds without freezing the app. What it
  heard is kept: `/model` typed again within 30 seconds doesn't ask again, and the palette and the
  list under the composer offer the discovered models from what the last `/model` heard (so run
  `/model` once to have them offered). Nothing else asks: not the status bar, not a launch.
- A server that isn't there, refuses the key, has no `/models`, or answers something else is one
  line under the list (`local: no list from http://localhost:11434/v1/models (can't connect: ...);
  its models are not listed`), never an error; the other models are listed as usual.
- An id is listed only if it is printable ASCII without a space, at most 200 characters, once its
  control characters are removed: a name is one word, and `/model` writes it into your session's layer
  file. A line under the list counts the entries it left out, whether an entry had no id or an id that
  isn't one.
- `discover` is read only from the models file in your config directory, like the rest of it. A
  `discover` in a layer (a `--patch`'s `extra`) is refused. A `claude-code` endpoint doesn't
  discover: name its models.
- The key goes only in the request's `Authorization` header, as for a chat request, and nothing
  the server says is shown but its ids and that line of why.

### The key

An `openai` endpoint gets its key one of two ways, or sends none (a local server).

A `key` names a line of `local.env`, never the key itself. For the example above, `local.env`
holds a line that sets `OPENROUTER_API_KEY`. The model row reads that line for each request and
sends it only as the request's `Authorization` header. The jail keeps the model's code from
reading `local.env`. A key may not name `CLAUDE_CODE_OAUTH_TOKEN`: that token is for Claude
Code alone, and a model whose key names it is refused. A key's line holds printable ASCII, as a key is issued: one that a request header can't carry (an
accented letter, say) is said in a line under `/model`'s list, and not sent.

A `key_command` is a command that prints the key instead, as a company's token tool or a password
manager's CLI does: `key_command = "op read op://work/openrouter/key"`. bh-02 runs it through your
shell, as you, when a request needs a key, and sends what it prints on stdout (trimmed) as that
request's `Authorization` header. The key is kept for `key_ttl_ms` (5 minutes when unset) so the
command doesn't run for every message, and dropped at once when the server refuses it. A command
that fails, takes over a minute or prints nothing is said with the command, never with anything it
printed. Give `key` or `key_command`, not both. Like `discover`, `key_command` is read only from the
models file: a layer's `extra` that names one is refused. A `claude-code` endpoint's `key_command`
is its gateway's ([above](#claude-through-a-gateway)), run by Claude Code itself.

### Keep the models file out of the project

bh-02 trusts the models file: a key it names is sent to the model's `base_url`, a `key_command` runs
as you, and a provider can be Python that runs in bh-02's own process. So the file must be somewhere the model's code can't
write. One inside the project bh-02 runs in, or reached through a link into it, is not read. This
happens when you run bh-02 from your home directory, where `~/.config` is part of the project.
Its models are not offered, and `/model` says why the file was passed over and where to put it
instead.

### When a model has a problem

A name that is no model, or a table with something wrong in it, is a message that says what to
fix. `/model` won't switch to it. A model chosen at launch that can't be used answers each
message with that message, and `/model` with another name gets you going again.

The models file is read when the model row starts and each time `/model` asks, not watched. An
edit takes effect at the next `/model` or launch; `/restart model` picks it up for the model
already chosen.

## A patch that sets the model

A `--patch` layer that gives the `model` row a `config` replaces the session's whole (its
`state`, where Claude Code's session is kept, too), so the patch chooses the model: the `default`
`/model` would write changes nothing. `--model` is refused with such a patch, and `/model` says it
can't switch. Set `default` in the patch instead, or put the models in the models file.
[Layers](layers.md) has more on patches.

The models plugin's own README has every setting and how each provider works:
[models-cordis-plugin](../reference/plugins/models.md).
