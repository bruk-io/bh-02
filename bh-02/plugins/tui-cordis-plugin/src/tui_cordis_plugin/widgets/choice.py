"""The choice modal: a question with named answers (CONTRACTS.md: choice), its keys drawn from the
question's `choices`. It is the approval modal with other answers: the same layout, the same
grace period before it answers (`ApprovalScreen`'s arming, not a copy of it), the same dimmed keys
line until then.
"""

from collections.abc import Mapping
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from tui_cordis_plugin import render
from tui_cordis_plugin.widgets.approval import GRACE, ApprovalScreen

__all__ = ["ChoiceScreen"]


class ChoiceScreen(ApprovalScreen[str]):
    """One question with the answers `choices` names. Each choice's key answers its `value`, and
    Escape answers the question's `escape`, when the key arrived after the grace period (as
    `ApprovalScreen`, whose `on_key` judges it); keys pressed before are dropped. Ctrl-C withdraws it, and the answer is then '' (nothing was chosen)."""

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

    def _key_answer(self, key: str) -> str | None:
        """A choice's key answers its value; Escape answers the question's `escape`."""
        if key == "escape":
            return str(self.question.get("escape", ""))
        return self._values.get(key)
