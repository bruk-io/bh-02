# Models

bh-02 runs one model at a time, chosen by name. `sonnet` is the default, unless your models file names another. You can start on
another, switch mid-session, and add models of your own.

## The built-in models

| Name | Provider | What it is |
|---|---|---|
| `sonnet` | `claude-code` | Claude Sonnet, through Claude Code on your subscription (the default) |
| `opus` | `claude-code` | Claude Opus, the same way |
| `haiku` | `claude-code` | Claude Haiku, the same way |

All three need the credential in `local.env` ([Get started](../get-started.md#the-credential)).

## Choosing a model

- **At launch**: `bh-02 --model opus`.
- **When resuming**: `bh-02 --resume --model haiku` carries the session on with another model.
- **Mid-session**: `/model` lists the models, with the current one marked `●`, the default one marked
  `(default: built in)` or `(default: the models file)`, each one's provider and id, and where your models file is. It also asks each
  endpoint you set to list its models ([below](#listing-an-endpoints-models-discover)). `/model NAME` switches to one. The
  conversation carries on: the transcript is a row of its own, and only the model row and what
  depends on it reload.

When you give neither, bh-02 starts on `sonnet`, or on the model your models file names as the
default ([below](#choosing-the-default)).

A switch is written into the session's own layer, so a resumed session keeps the model you last
chose. The status bar shows the model and its provider, `model: sonnet (claude-code)`, and
`starting…` while a new one comes up; a model that can't be used shows `(unusable)` instead of
looking like one that runs.

## Choosing the default

Put `default = "NAME"` at the top of the models file, above the first table, to start new
sessions on one of your models without a flag:

```toml
default = "local"

[local]
provider = "openai"
id = "qwen3-coder"
base_url = "http://localhost:11434/v1"
```

A new session takes the default when it starts and records it in its own layer, as `--model`
does, so it keeps that model when you resume it, whatever the file says later; change the file
and only new sessions move. What a new session starts on, strongest first: `--model`, the
models file's `default`, and `sonnet`. `/model` still switches mid-session.

The default must be a model's name. A default bh-02 can't use never quietly becomes a Claude
model, since the default chooses what you spend: the session starts, the model row says what to
write at your first message (a default that is not a name, a number say, or names no model: `no
model named 'gone', the default in the models file ...`), the status bar says `model: default
(unusable)` or `gone (unusable)`, and `/model` lists the models and a line saying the default is
refused and why. `/model NAME` of a model that works switches, and so does `--model`; such a
session is listed by `bh-02 sessions` as started on `default`. Like the models themselves, the
default is read only from the models file in your config directory, never from one in the
project.

If the models file itself can't be read (not TOML, a key that is no table, a path that is no
file), the built-in models still work: `/model sonnet` switches, the first message says what is
wrong with the file, and `/model` ends with that problem in place of where to add models.

## Adding your own: the models file

Your models go in `~/.config/bh-02/models.toml` (`$XDG_CONFIG_HOME/bh-02/models.toml` when that
variable is set), one table per model. The table's name is the model's name in bh-02.

```toml
[local]
provider = "openai"
id = "qwen3-coder"
base_url = "http://localhost:11434/v1"

[router]
provider = "openai"
id = "anthropic/claude-sonnet-4"
base_url = "https://openrouter.ai/api/v1"
key = "OPENROUTER_API_KEY"
```

Then `/model local`, or `bh-02 --model router`.

| Setting | What it is |
|---|---|
| `provider` | `claude-code` (Claude through Claude Code) or `openai` (any OpenAI-compatible `/chat/completions` endpoint) |
| `id` | the model's id at that provider |
| `base_url` | `openai` only: the endpoint, ending before `/chat/completions` |
| `key` | `openai` only, optional: the **name** of a line in `local.env` that holds the API key |
| `max_tokens`, `temperature` | `openai` only, optional: sent with each request when set |
| `discover`, `include` | `openai` only, optional: `discover = true` makes the table an endpoint that lists its models, `include` narrows them ([below](#listing-an-endpoints-models-discover)) |

The `openai` provider works with OpenAI, OpenRouter, Groq, Together, Mistral, xAI, DeepSeek,
Gemini's compatibility endpoint, vLLM, LM Studio and Ollama (at `/v1`). A `claude-code` table can
name another Claude model by its id.

A model of yours with a built-in's name takes its place, and `/model` says so.

### Listing an endpoint's models: discover

A server you run yourself may serve many models, and one table each is a chore. Give the
endpoint one table with `discover = true` instead:

```toml
default = "local/qwen2.5-coder:7b"

[local]
provider = "openai"
discover = true
base_url = "http://localhost:11434/v1"
include = ["qwen*", "llama3*"]    # optional: only the ids matching one of these globs
```

`/model` then asks the server which models it has (`GET <base_url>/models`) and lists each as
`local/ID`: `local/qwen2.5-coder:7b`, `local/llama3.2:latest`. The name is the table's name, a
`/`, and the server's id, split at the first `/`, so an id may hold more of them (`local/Qwen/Qwen2.5-Coder`)
and `:`. `/model local/qwen2.5-coder:7b`, `bh-02 --model local/qwen2.5-coder:7b`, a layer's
`default` and the models file's `default` all take such a name, and none of them asks the server:
`local/ID` means the model `ID` on that endpoint, whether or not the server lists it, so bh-02 starts
and switches with the server down. An id the server doesn't have is that first message's 404.

What to know:
- The endpoint is not a model itself: it takes no `id`, and `--model local` says to name one of its
  models. It takes `key`, `max_tokens` and `temperature` as any `openai` table does, and its models
  share them. The table's name may not hold `/`. A table with something wrong in it (an `id` beside
  `discover`, a bad `include` or `base_url`) names no models either: `local/ID` is refused, as a
  model of any table with a problem is, with that table's problem and what to write.
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
- Endpoints are read only from the models file in your config directory, like the rest of it. A
  `discover` in a layer (a `--patch`'s `extra`) is refused.
- The key goes only in the request's `Authorization` header, as for a chat request, and nothing
  the server says is shown but its ids and that line of why.

### The key

A `key` names a line of `local.env`, never the key itself. For the example above, `local.env`
holds a line that sets `OPENROUTER_API_KEY`. The model row reads that line for each request and
sends it only as the request's `Authorization` header. The jail keeps the model's code from
reading `local.env`. A key may not name `CLAUDE_CODE_OAUTH_TOKEN`: that token is for Claude
Code alone, and a model whose key names it is refused. A key's line holds printable ASCII, as a key is issued: one that a request header can't carry (an
accented letter, say) is said in a line under `/model`'s list, and not sent.

### Keep the models file out of the project

bh-02 trusts the models file: a key it names is sent to the model's `base_url`, and a provider can
be Python that runs in bh-02's own process. So the file must be somewhere the model's code can't
write. One inside the project bh-02 runs in, or reached through a link into it, is not read. This
happens when you run bh-02 from your home directory, where `~/.config` is part of the project.
The built-in models still work, and `/model` says why the file was passed over and where to put
it instead.

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
