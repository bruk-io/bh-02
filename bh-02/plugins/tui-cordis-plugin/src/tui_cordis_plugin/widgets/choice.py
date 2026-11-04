"""The choice modal: a question with named answers (CONTRACTS.md: choice), its keys drawn from the
question's `choices`. It is the approval modal with other answers: the same layout, the same
grace period before it answers (`ApprovalScreen`'s arming, not a copy of it), the same dimmed keys
line until then.
"""

from collections.abc import Mapping
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.widgets import Static

from tui_cordis_plugin import render
from tui_cordis_plugin.widgets.approval import GRACE, ApprovalScreen

__all__ = ["ChoiceScreen"]


class ChoiceScreen(ApprovalScreen[str], inherit_bindings=False):
    """One question with the answers `choices` names. Each choice's key answers its `value`, and
    Escape answers the question's `escape`, once `armed` (as `ApprovalScreen`); keys pressed
    before are dropped. Ctrl-C withdraws it, and the answer is then '' (nothing was chosen)."""

    BINDINGS = []

    def __init__(self, question: Mapping[str, Any], *, grace: float = GRACE) -> None:
        super().__init__(question, grace=grace)
        self._values = {key: value for key, value, _ in render.choices_of(question)}

    def compose(self) -> ComposeResult:
        with Vertical(id="approval"):
            yield Static(render.choice_heading(self.question), id="approval-title", markup=False)
            for line in self.question.get("lines") or ():
                yield Static(str(line), classes="approval-line", markup=False)
            if warning := str(self.question.get("warning") or ""):
                yield Static(f"Warning: {warning}", id="approval-warning", markup=False)
            yield Static(
                render.choice_keys(self.question), id="approval-keys", classes="-arming", markup=False
            )

    def on_key(self, event: Key) -> None:
        """A choice's key, or Escape, answers once armed; either way it goes no further (a key
        dropped while arming must not reach the app's bindings, Escape's among them)."""
        key = event.key.lower()
        if key == "escape":
            event.stop()
            self.action_answer(str(self.question.get("escape", "")))
        elif key in self._values:
            event.stop()
            self.action_answer(self._values[key])
