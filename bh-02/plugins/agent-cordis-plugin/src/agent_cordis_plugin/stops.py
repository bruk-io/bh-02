"""Why a model step stopped, and what the loop does about it: pure.

"No tool call" is three different things, and only one of them is done:

| finish        | call | text  | means                            |
|---------------|------|-------|----------------------------------|
| (any)         | yes  |       | act                              |
| stop          | no   | prose | answered: the only real done     |
| length        | any  |       | truncated: cut off, maybe mid-call |
| stop          | no   | none  | silent: said nothing             |

and a fourth, one level down: a call the model made whose arguments would not decode
(undecodable). A step the provider refused (`refusal`) is none of these: it is `refused`,
never run and never fed back, since asking again won't change the answer. The rule for all
of them: never synthesize an action the model did not call; always decode one it did. A step
that is not `act`, `answered` or `refused` is fed back to the model, never read as its answer.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Final

__all__ = ["ACT", "ANSWERED", "FEEDBACK", "REFUSED", "SILENT", "TRUNCATED", "UNDECODABLE", "classify"]

ACT: Final = "act"
ANSWERED: Final = "answered"
TRUNCATED: Final = "truncated"
SILENT: Final = "silent"
UNDECODABLE: Final = "undecodable"
REFUSED: Final = "refused"

# Every provider's word for "hit the output limit" (Anthropic's `model_context_window_exceeded`
# is the same cut, at the context window instead of `max_tokens`).
_TRUNCATION: Final = frozenset({"length", "max_tokens", "model_context_window_exceeded"})
# The provider declined the request (Anthropic's `refusal`): whatever came so far, a call cut
# off mid-input included, is not an action, and asking again is not a fix.
_REFUSAL: Final = frozenset({"refusal"})

FEEDBACK: Final[Mapping[str, str]] = {
    TRUNCATED: (
        "Your last message hit the output token limit before it finished, so nothing ran. "
        "Send less at once: write a long file over several inputs (open(path, 'a') appends to "
        "it), or say less before the call."
    ),
    SILENT: "Your last message was empty. Call the tool, or say what you found.",
    UNDECODABLE: (
        "Your last tool call could not be decoded -- its arguments were not valid JSON. Send the call again."
    ),
}


def classify(finish: str | None, text: str, calls: Sequence[Mapping[str, Any]]) -> str:
    """What the loop should do next about one completed model step.

    `finish` is the provider's own stop reason, if it gave one; `calls` are the tool calls
    the step carried, each with an `error` when its arguments did not decode.
    """
    if finish in _REFUSAL:
        return REFUSED
    if any(call.get("error") for call in calls):
        return UNDECODABLE
    if finish in _TRUNCATION:
        return TRUNCATED
    if calls:
        return ACT
    return ANSWERED if text.strip() else SILENT
