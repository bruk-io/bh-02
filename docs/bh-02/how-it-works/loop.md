# The loop

The agent loop is bh-02's own row, `agent:loop`. It sends the conversation to the model, runs the
tool calls the model asks for, and decides when a reply is done. Every model goes through the same
loop: only the model row's provider differs.

## A turn

A turn is the reply to one message. It takes one model step or more:

1. The loop sends the model the conversation: the system prompt, then the transcript. It offers
   the tools rows have registered with `tools` (`agent:tools`, a broker), through the provider's
   standard tool calling. In the shipped composition that is one tool, `python`.
2. The model answers, or asks for calls to its tools.
3. The loop asks `approval` whether each call may run, runs it through the tool its name has (a
   `python` call is an **input** to the Python process), and adds the tool's answer to the
   transcript as the call's result, with any notes rows add
   ([The prompt and notes](prompt-and-notes.md)).
4. Back to 1, until the model answers without asking for a call.

A call to a tool the loop did not offer, or one whose input doesn't fit the tool's spec (a
`python` call without `code`), is answered with text saying so, and nothing runs. A call
`approval` turns down is answered with that.

## The tools

The loop reads the list of tools at a conversation's first request, after the ones its
`requires` names have registered (the shipped layer requires `python`; a message typed right
after `/clear`, when the kernel is starting again, says it waits), and keeps it in the
transcript. It offers that same list, in name order, for the rest of the conversation: the list
is the start of what a model server caches, so a list that changed would cost the cache.

When the tools change partway through (an extension registers one, a layer edit adds a row),
the loop keeps the change in the transcript and tells the model on the next message it reads,
the way it tells a changed system prompt, and you see "told the model its tools changed since
the conversation began". The list offered stays as it was: an added tool is offered from the
next conversation (`/clear` or `/compact`), and a call to a removed one doesn't run. A resumed
session sends the same requests it would have. A tool's row tells the model about its tool in a
section of the system prompt, never in the tool's description.

The transcript is a row of its own (`agent:transcript`), written to the session's
`transcript.jsonl`. So a `/model` switch, which reloads the loop, keeps the conversation.

## Steps that don't count

The loop classifies every step. Only a step that asks for calls runs them, and only a step that
answers ends the reply. A step that was cut off, said nothing, or asked for a call that can't be
read doesn't count: the loop tells the model why (a nudge) and asks again, up to `max_nudges` times
a reply (2 by default). So a cut-off step is never taken for the answer.

## Stopping a reply

`Ctrl+C` stops the reply, and the loop closes the model step: the `claude-code` provider
interrupts Claude Code, the `openai` provider closes its stream. Every call the model asked for is
still answered in the transcript: the one running as interrupted (it may have partly run), the
rest as not run. The stopped reply stays in the transcript with what it said and that it was
stopped, so your next message doesn't redo it.

## The model row and its providers

The `model` row (`models:model`) is one model step per call. Two providers fill it:

- **`claude-code`**: Claude through Claude Code (the Claude Agent SDK), the route your
  subscription supports. Claude Code only carries steps: it runs none of its own tools, loads no
  settings or `CLAUDE.md`, and doesn't compact. The `python` tool is declared to it through an
  in-process MCP server and never runs there: a call waits for the loop's next request to bring
  its result. One Claude Code process holds a conversation, and its state is kept in the session's
  `claude/` directory, so `--resume` continues it.
- **`openai`**: any OpenAI-compatible `/chat/completions` endpoint, one streamed request a step.

Because the loop, not the provider, runs the calls, approval is in one place for every model, and
nothing in the loop depends on which provider answers.

The agent plugin's README has the loop in full ([agent-cordis-plugin](../reference/plugins/agent.md)),
and the models plugin's README has both providers
([models-cordis-plugin](../reference/plugins/models.md)).
