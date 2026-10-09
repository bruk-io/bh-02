# Models

bh-02 runs one model at a time, chosen by name. `sonnet` is the default. You can start on
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
- **Mid-session**: `/model` lists the models, with the current one marked `●`, each one's
  provider and id, and where your models file is. `/model NAME` switches to one. The
  conversation carries on: the transcript is a row of its own, and only the model row and what
  depends on it reload.

A switch is written into the session's own layer, so a resumed session keeps the model you last
chose. The status bar shows the model and its provider, `model: sonnet (claude-code)`, and
`starting…` while a new one comes up.

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

The `openai` provider works with OpenAI, OpenRouter, Groq, Together, Mistral, xAI, DeepSeek,
Gemini's compatibility endpoint, vLLM, LM Studio and Ollama (at `/v1`). A `claude-code` table can
name another Claude model by its id.

A model of yours with a built-in's name takes its place, and `/model` says so.

### The key

A `key` names a line of `local.env`, never the key itself. For the example above, `local.env`
holds a line that sets `OPENROUTER_API_KEY`. The model row reads that line for each request and
sends it only as the request's `Authorization` header. The jail keeps the model's code from
reading `local.env`. A key may not name `CLAUDE_CODE_OAUTH_TOKEN`: that token is for Claude
Code alone, and a model whose key names it is refused.

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

A `--patch` layer that gives the `model` row a `config` replaces the session's whole, so the
patch chooses the model. `--model` is refused with such a patch, and `/model` can't switch. Set
`default` in the patch instead, or put the models in the models file. [Layers](layers.md) has
more on patches.

The models plugin's own README has every setting and how each provider works:
[models-cordis-plugin](../reference/plugins/models.md).
