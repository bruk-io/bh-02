# The prompt and notes

What the model reads each step is its context: the system prompt, then the transcript. This page
covers the prompt, why it stays fixed for a conversation, and the notes the loop adds to an
input's result.

## What the system prompt says

The `system` row (`agent:system`) builds the prompt, in the order Claude Code builds its own:

1. who the model is (the model in bh-02) and what bh-02 is made of;
2. where it is working: the directory and its git branch;
3. the sections other rows add, sorted by name: how to extend bh-02 with extensions of its own,
   memory's instruction files ([Memory](../using/memory.md)) and auto memory, and the `python`
   tool's instructions (the python row's section): what the tool is, how to use it, and, under a
   Linux jail, what its code can read.

The prompt names no tool itself: the tools are the rows' that register them with `tools`, and a
tool's row says what the model should know of it in a section of its own.

`system` is a broker: a row with something to tell the model registers a section, and the
section goes when the row does.

## Why the prompt stays fixed for a conversation

This page is where bh-02 says why; the rest of the docs point here.

A model server reuses its work on a conversation only up to the first token that differs from the
last request, and a request begins with the tool list and the system prompt. If either changed
partway through, the whole conversation would be new to it: a local model would spend minutes on
prompt processing before the first new token (it looks frozen), a hosted one would bill it
uncached, and Claude Code would have to restart on its session and lose its cache. So what a
conversation began with is sent unchanged for its life, and a change is told as a note on the
next message instead, which comes after the cached start.

**The prompt.** The loop sends the prompt the conversation began with, every time. It is kept as the
transcript's first entry. Before each message the model reads, the loop reads the prompt again; when
something has changed (an extension loaded, the branch switched, a `CLAUDE.md` edited), it tells the
model what changed as a note on that message, and you see the note too. The transcript keeps each
change as the edits from the reading before it, not as a whole new copy, so it holds the prompt once
however often it changes, and the loop applies them in turn to know what it last told.

**The tool list.** The loop reads the list of tools at a conversation's first request and keeps it
in the transcript too. Before each message the model reads, it reads the list again: a tool added,
removed or redefined since is kept as another entry and told on that message (by name, the start of
its description and its input's names), and you see "told the model its tools changed since the
conversation began". Which list a request offers is the model's provider's to say (`tool_changes`):
`fixed`, the list the conversation began with, for its life, or `listed`, the list as the transcript
last recorded it. Both shipped providers say `fixed`, since a changed list would cost each of them
the cache: an OpenAI-compatible server renders the list at the start of the prompt (llama.cpp,
Ollama, vLLM, LM Studio, and OpenAI's own cache is a prefix of the request), and Claude Code sends
the tools first too. So an added tool is offered from the next conversation, and a call naming it
before then says so, though an input can call it at once (`tools.NAME(...)`, [The python
tool](python-tool.md)). For the same reason a tool's row tells the model about its tool in a section
of the prompt, never in the tool's description, which a model server caches with the list. The
models plugin's README has what each provider would do with a changed list
([models-cordis-plugin](../reference/plugins/models.md)).

**The date.** The date is not in the prompt either, or the prompt would change every midnight. The
loop tells it with your message instead, `(Today's date: ...)`, on the first message of a
conversation and the first of each day. A resume on the same day doesn't tell it again; `/clear` and
`/compact` do. So the prompt reads the same from day to day, and a local model server that keeps its
prompt cache can reuse a new session's start.

A resumed session reads the prompt it began with, its edits and its tool lists from its
transcript, so it sends the same requests it would have. `/clear` and `/compact` begin a new
conversation, and with it a fresh reading of the prompt and the tools.

## Notes after a call

After each call, the loop asks `notes` (`agent:notes`, another broker) what to tell the model with
its result. Each function a row has added there gets the tool's name, the call's input, its result
and the files it opened, as its tool answered (for a `python` input, what its own Python code
opened, its `touched()`). It may add a note; it can't change the result.

The shipped one is memory's on-demand loading (`memory:on_touch`): the first time an input in a
conversation opens a file that a subdirectory's `CLAUDE.md`, or a rule with matching `paths`,
covers, that file arrives whole as a note, as Claude Code's do when its own tools touch one. Its notes
for one result are capped at 20,000 characters; a file that didn't fit comes with a later input
that opens a file it covers.

## Asked before a file is written

A note arrives after the call, so an input that reads a file and writes it in one go would write
it before seeing the instructions for it. So bh-02 can also be asked *before* a file is opened
(`access`, `agent:access`, another broker): a tool asks, and a row may refuse. Memory's on-touch
row refuses the first write to a file whose on-demand instructions this conversation hasn't been
told: the input gets a `PermissionError` at that line, the file is untouched, and the
instructions arrive with the result, so the model's next write goes ahead. That's Claude Code's
rule that Edit and Write need a Read first, in bh-02's terms.

What it doesn't do:

- **It only hears what the tool reports.** The `python` tool asks from inside its Python process,
  so it hears Python's own `open()` and `pathlib` of a project file. A program the input runs
  (`sed -i`, `git apply`, a formatter), `os.open`, a rename, a replace or a delete isn't asked
  about. Another tool asks only if its author made it. The jail is what enforces; this is a way
  to say something first.
- **The model hears nothing until the call ends.** A refusal stops one open; the input may be half
  done. If its code caught the error, the refusal is still told at the end of the result.
- **Reads aren't refused** by anything bh-02 ships; a row of yours can ask about them, at the cost
  of a question for each file an input reads.

Only rows in a layer add to `notes`, since its functions run in bh-02's own process.

## Off the app's event loop

Reading the prompt can mean reading many files, and so can a note. Both run on the `executor` row,
in a thread, never on the event loop the app shares, so a slow section never freezes the app; a
section or a note must not need the event loop. One reading runs at a time, and nothing stops one
part-way: if you stop a reply while one runs, the next waits for it rather than starting another
beside it. `executor` depends on nothing, so `/clear` and `/model`, which reload the loop, keep it
and the reading in flight: stopping reply after reply leaves at most one running. Its thread is a
daemon's, so a reading left running never holds bh-02 open as it exits.

The agent plugin's README has the full account: [agent-cordis-plugin](../reference/plugins/agent.md).
