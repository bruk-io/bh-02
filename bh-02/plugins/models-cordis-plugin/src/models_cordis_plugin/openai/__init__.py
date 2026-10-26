"""Any OpenAI-compatible `/chat/completions` endpoint: the `openai` provider of the `model` row."""

from models_cordis_plugin.openai.client import OpenAIModel, headers_for, missing_key
from models_cordis_plugin.openai.discovery import Ask, Discovery, Get, ListingKey, httpx_get
from models_cordis_plugin.openai.listing import (
    SHOWN,
    Down,
    Listed,
    Reply,
    Unlisted,
    matching,
    models_url,
    notes,
)
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
    "SHOWN",
    "Ask",
    "Discovery",
    "Down",
    "Fold",
    "Get",
    "ListingKey",
    "Listed",
    "OpenAIModel",
    "Reply",
    "Unlisted",
    "Where",
    "headers_for",
    "http_error",
    "httpx_get",
    "matching",
    "missing_key",
    "models_url",
    "notes",
    "rejects_usage",
    "replayed",
    "request_for",
    "sse_data",
    "stop_for",
    "stream_error",
]
