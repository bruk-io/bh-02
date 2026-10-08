# The loop

The agent loop is bh-02's own row, `agent:loop`. It sends the conversation to the model, runs the
code the model asks to run, and decides when a reply is done. Every model goes through the same
loop: only the model row's provider differs.

## A turn

A turn is the reply to one message. It takes one model step or more:

1. The loop sends the model the conversation: the system prompt, then the transcript. It offers
   one tool, `python`, through the provider's standard tool calling.
2. The model answers, or asks for calls to `python`.
3. Each call is an **input**. The loop asks `approval` whether it may run, runs it in the Python
   process (`kernel.run(code)`), and adds what it printed to the transcript as the call's result,
   with any notes rows add ([The prompt and notes](prompt-and-notes.md)).
4. Back to 1, until the model answers without asking for a call.

A call to any other tool, or one without `code`, is answered with text saying so, and nothing
runs. A call `approval` turns down is answered with that.

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
