# bh-02

Programs made of parts that can be added, replaced and removed while they run, with every change
undone in the right order. This repository is that pattern, **cordis**, and two programs built
with it: **bh-02**, a coding agent, and **warden**, a process supervisor.

cordis is a Python realisation of *A Programming Paradigm for Spatiotemporal Composability*
(Shi, Zhang, Cui, arXiv:2608.25512). It knows nothing about agents, models or user interfaces.
[`libs/cordis/README.md`](libs/cordis/README.md) is the full design doc; this page is the short
version.

## The pattern

**One rule.** A component is an async generator that yields effects. Its keyword-only
parameters are its dependencies, `config` is its configuration, and what it provides is what it
binds:

```python
@component
async def price_feed(*, feed: Feed) -> Effects:
    sub: Sub = yield subscribe(feed)             # an effect: a step and its undo, as a value
    buffer: list[float] = []
    yield background(pump(sub, buffer))          # work this component owns
    yield bind("recent_prices", lambda n=10: buffer[-n:])   # what it provides, under a key
```

The component never touches the runtime. The runtime performs every effect, records every undo,
and runs the undos in reverse when the component leaves.

**Keys, not imports.** Parts agree on a name, never on code. A consumer declares what it needs as
a parameter named after the key, and annotates it with a `Protocol` of its own. cordis checks the
bound value against that contract before the consumer's first effect. So a provider and a
consumer can be written by people who have never met, and one provider can satisfy two
consumers' different contracts.

**Reactive by construction.** A component runs only while every dependency is bound, and unloads
before any of them is unbound. Replacing a binding reloads exactly the components that depend on
it, and nothing else. A failure during setup reverts only what landed.

**Rows and layers.** A running program is a list of rows, each an `id`, the component that fills
it (`use`), and its `config`. Rows come from layer files applied in order: a new id adds a row,
an existing id replaces its fields. The loader watches those files, so **editing a layer reshapes
the running program**. Whoever edits it, a person, a script or a model, changes the program
through the same mechanism, and cordis swaps only what changed.

**Brokers.** For a collection many parts contribute to, one row binds the collection and the
others `acquire` an entry in it. The registration's return value is its remover, so an entry
leaves with the part that added it and nothing else reloads.

These guarantees are asserted as the paper's theorems over random histories of operations, in
[`libs/cordis/tests/test_invariants.py`](libs/cordis/tests/test_invariants.py).

## What's here

| Path | What it is |
|---|---|
| [`libs/cordis`](libs/cordis) | the pattern: components, effects, keys, fibers, rows, layers, the loader |
| [`libs/cordis-helpers`](libs/cordis-helpers) | small building blocks on cordis: a broker's registry, a set of hooks |
| [`libs/brig`](libs/brig) | a sandbox library, independent of cordis: a spec compiled into honestly graded enforcement |
| [`bh-02`](bh-02) | a coding agent built as cordis rows: its app in `app/`, its plugins in `plugins/` |
| [`examples/warden`](examples/warden) | a process supervisor built the same way, with no model in it |

## bh-02: the pattern applied to a coding agent

Everything bh-02 is, is a row in [`bh-02.toml`](bh-02/app/src/bh_02/bh-02.toml), filled by a
plugin:

| Row | Filled by | What it is |
|---|---|---|
| `model` | `models:model` | the model: Claude via Claude Code, or any OpenAI-compatible endpoint |
| `loop` | `agent:loop` | the agent loop: sends the conversation, runs the tool calls |
| `kernel` | `kernel:kernel` | the one tool, `python(code)`: a persistent Python kernel |
| `jail` | `brig:jail` | where the kernel runs: brig's sandbox |
| `ui` | `tui:app` | the terminal app, on [bh-01](https://github.com/bruk-io/bh-01)'s design tokens |
| `chat`, `transcript`, `system`, `commands`, ... | | the conversation, its record, the project context, the slash commands |

No plugin imports another; they agree on keys and shapes, written down in
[`bh-02/CONTRACTS.md`](bh-02/CONTRACTS.md). So each part is swapped with one line in a layer:
another model, another jail, another interface. `/model opus` edits the session's own layer
file and the loader swaps the model row, while the conversation carries on. `/clear` restarts
three rows. `/rows` shows the program as it is running. [`bh-02/GLOSSARY.md`](bh-02/GLOSSARY.md)
defines every term.

### Running it

You need [uv](https://docs.astral.sh/uv/) and Python 3.15 (uv fetches it). The sandbox runs on
macOS; elsewhere, pass `--no-jail`.

```sh
git clone https://github.com/bruk-io/bh-02 && cd bh-02
uv sync --all-packages
claude setup-token                        # Claude Code makes a token for your subscription
echo 'CLAUDE_CODE_OAUTH_TOKEN=<the token>' > local.env && chmod 600 local.env   # git-ignored
cd ~/some/project && ~/path/to/bh-02/.venv/bin/bh-02
```

The model acts in Python, at a REPL of its own that persists for the session. In the sandbox its
code runs without asking: it can write inside
the project, but it can't reach the network, read credentials, or touch what could run code later
(`.git/hooks`, shell rc files, bh-02's own layers). With `--no-jail`, every input asks first.
Ctrl-C stops a reply, Ctrl-P opens the command palette, `bh-02 --resume` continues a session.

`sonnet`, `opus` and `haiku` are built in. Add any OpenAI-compatible model (OpenAI, OpenRouter,
Groq, vLLM, LM Studio, Ollama, ...) to `~/.config/bh-02/models.toml`, then `/model NAME`:

```toml
[qwen]
provider = "openai"
id = "qwen3-coder"
base_url = "http://localhost:11434/v1"
key = "SOME_API_KEY"          # optional: the name of a line in local.env, never the key itself
```

### Changing it

A layer of your own changes a row, applied with `bh-02 --patch mine.toml`:

```toml
[[plugin]]
id = "jail"
config = { allow = ["CLAUDE.md", "AGENTS.md", ".git/config"] }   # let inputs write .git/config too
```

A new part is a plugin: a package with components, registered as a `cordis.plugins` entry point,
named by a row. [`bh-02/CLAUDE.md`](bh-02/CLAUDE.md) walks through adding one.

The model can extend bh-02 too, while it runs: a module of cordis components it writes to
`.bh-02/plugins/` in the project is loaded at once, in a jail of its own, and can add a slash
command, a status-bar field or text in the model's own prompt, each taken back when the file
changes or goes ([`extensions-cordis-plugin`](bh-02/plugins/extensions-cordis-plugin)).

## warden: the same pattern, no model

[`examples/warden`](examples/warden) supervises processes. Each process is a row that registers
itself with a broker, so adding, removing or reconfiguring one (by editing the layer, while
warden runs) never restarts another. It shares nothing with bh-02 but cordis, which is the point:
the pattern isn't about agents.

## cordis in practice

The techniques above, and where to read them in real code:

| Technique | Implemented in | What it shows |
|---|---|---|
| **A resource's lifetime is a row's** (`enter`) | `warden:supervised`, `kernel:kernel`, `tui:app` | a process starts when its row loads and is terminated when it unloads; the kernel's worker lives exactly as long as the `kernel` row; the terminal app's lifetime is the `ui` row's |
| **A broker** (`acquire`, the remover as undo) | warden's `processes`; bh-02's `commands` and `frame` | each supervised process registers itself; slash commands register into `commands`; the status bar, sidebar and palette are entries rows `acquire` in the app's `frame`, gone when their row goes |
| **One key, swappable providers** | bh-02's `model`, `jail`, `ui` rows | Claude or any OpenAI-compatible model behind `model`; brig's sandbox or none behind `jail`; tests put fakes in the same rows with `--patch` (`bh_02.testing`) |
| **Reshaping by editing a layer** | `/model` (bh-02); adding a process (warden) | `/model opus` writes the session's layer file and the loader swaps one row; a new `[[plugin]]` block in warden's layer starts one more process, touching nothing else |
| **An operator over the loader** | `commands:operator` | `/rows`, `/explain`, `/restart` and `/clear` act on the running program through the loader's handle, queued as the operator row's own background work so a restart never cancels the command asking for it |
| **Work a row owns, and its end** (`background`, `done`) | `chat:session`, bh-02's bootstrap | the conversation is the chat row's background task, bound as `done`; the bootstrap waits on it and follows a new `done` when the chat row reloads, so `/model` never ends the session |
| **Watching the program change** (`observe`) | `tui:app` | the terminal app hears every lifecycle event and shows `↻ model reloaded` as rows reload |
| **Two consumers, two contracts** | the `kernel` key | the agent loop needs its tool (`spec`, `run`); the status row needs its grades (`confined`, `report`); each declares its own Protocol for the same value |
| **Stable rows around volatile ones** | bh-02's `ui` and `status` rows | the app's row depends on nothing but its config, so it never reloads; the small `status` row depends on `kernel`, so `/clear` reloads it and not the screen |
| **Who owns the main thread** | `warden --tray` | the macOS menu-bar app needs the main thread, so the composition runs on a background thread and quitting the tray unwinds it through the same shutdown |

## brig: sandboxes that say what they enforce

[`libs/brig`](libs/brig) runs untrusted processes in a jail. A `Spec` describes the jail
(filesystem, network, limits, environment, channels), and mechanisms compile parts of it and
compose into a stack: Seatbelt on macOS, bubblewrap and cgroups on Linux, an egress proxy,
rlimits, environment scrubbing, containers.

Its central idea is **honest grading**. Every axis of enforcement is reported as `enforced`,
`best_effort`, `cooperative` or `unenforced`, according to what the stack can actually deliver,
and `probe()` proves the grades by attempting violations from inside the jail. A sandbox that
quietly enforces less than you asked for is worse than none; brig says exactly what you got.

brig stands alone: it imports only the standard library, knows nothing of cordis or bh-02, and
has its own architecture gate. bh-02 reaches it through one plugin, `brig:jail`, which turns
bh-02's rules into a `Spec`: the project writable, bh-02's own files and credentials not, no
network. bh-02's status bar shows the grades it got (`jail: jailed fs_write ✓ network ✓ ...`).
bh-02 wires only the macOS stack today. [`libs/brig/SPEC.md`](libs/brig/SPEC.md) is its
contract.

## Development

```sh
scripts/check                              # format, lint, types, tests and the architecture gates
scripts/check libs/cordis                  # the same for one package
uv run pytest libs/cordis/tests/test_invariants.py -q   # the paper's theorems
```

The boundaries (no plugin imports another, only a plugin's `wiring.py` and the app's shell know cordis, pure
functions by default) are checked by [pypeeker](https://github.com/brukhabtu/pypeeker) gates, not
by convention. [`CLAUDE.md`](CLAUDE.md) is the guide to working here.

## License

[AGPL-3.0-or-later](LICENSE).
