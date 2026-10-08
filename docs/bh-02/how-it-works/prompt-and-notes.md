# The prompt and notes

What the model reads each step is its context: the system prompt, then the transcript. This page
covers the prompt, why it stays fixed for a conversation, and the notes the loop adds to an
input's result.

## What the system prompt says

The `system` row (`agent:system`) builds the prompt, in the order Claude Code builds its own:

1. who the model is (the model in bh-02) and what bh-02 is made of;
2. where it is working: the directory and its git branch;
3. the sections other rows add: memory's instruction files ([Memory](../using/memory.md)), auto
   memory, and how to extend bh-02 with extensions of its own.

The loop follows it with the `python` tool's instructions: what the tool is, how to use it, and,
under a Linux jail, what its code can read.

`system` is a broker: a row with something to tell the model registers a section, and the
section goes when the row does.

## Why the prompt stays fixed for a conversation

A model server reuses its work on a conversation only up to the first token that differs from the
last request. If the prompt at the start changed, the whole conversation would be new to it: a
local model would spend minutes on prompt processing before the first new token (it looks
frozen), and Claude Code would have to restart and lose its cache.

So the loop sends the prompt the conversation began with, every time. It is kept as the
transcript's first entry. Before each message the model reads, the loop reads the prompt again;
when something has changed (an extension loaded, the branch switched, a `CLAUDE.md` edited), it
tells the model what changed as a note on that message, and you see the note too. The transcript
keeps each change as the edits from the reading before it, not as a whole new copy.

The date is not in the prompt either, or the prompt would change every midnight. The loop tells it
with your message instead, `(Today's date: ...)`, on the first message of a conversation and the
first of each day. A resume on the same day doesn't tell it again; `/clear` and `/compact` do. So
the prompt reads the same from day to day, and a local model server that keeps its prompt cache
can reuse a new session's start.

`/clear` and `/compact` begin a new conversation, and with it a fresh reading of the prompt.

## Notes after an input

After each input, the loop asks `notes` (`agent:notes`, another broker) what to tell the model with
its result. Each function a row has added there gets the input's code, its result and the project
files it opened (`kernel.touched()`). It may add a note; it can't change the result.

The shipped one is memory's on-demand loading (`memory:on_touch`): the first time an input in a
conversation opens a file that a subdirectory's `CLAUDE.md`, or a rule with matching `paths`,
covers, that file arrives whole as a note, as Claude Code's do when its own tools touch one. Its notes
for one result are capped at 20,000 characters; a file that didn't fit comes with a later input
that opens a file it covers.

Only rows in a layer add to `notes`, since its functions run in bh-02's own process.

## Off the app's event loop

Reading the prompt can mean reading many files, and so can a note. Both run on the `executor` row,
in a thread, never on the event loop the app shares. One reading runs at a time: if you stop a
reply while one runs, the next waits for it rather than starting another beside it. `executor`
depends on nothing, so `/clear` and `/model` keep it.

The agent plugin's README has the full account: [agent-cordis-plugin](../reference/plugins/agent.md).
