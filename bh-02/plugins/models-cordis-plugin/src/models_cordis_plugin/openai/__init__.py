"""Any OpenAI-compatible `/chat/completions` endpoint: the `openai` provider of the `model` row."""

from models_cordis_plugin.openai.client import OpenAIModel, authorization, missing_key
from models_cordis_plugin.openai.wire import (
    Fold,
    Where,
    http_error,
    rejects_usage,
    replayed,
    request_for,
    sse_data,
    stop_for,
    stream_error,
)

__all__ = [
    "Fold",
    "OpenAIModel",
    "Where",
    "authorization",
    "http_error",
    "missing_key",
    "rejects_usage",
    "replayed",
    "request_for",
    "sse_data",
    "stop_for",
    "stream_error",
]
