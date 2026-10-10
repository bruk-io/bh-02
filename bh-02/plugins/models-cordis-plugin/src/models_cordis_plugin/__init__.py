"""bh-02's model row: named models over their providers, bound under `model`; `models`, the
models there are; and `/model`, which lists them and switches by name."""

from models_cordis_plugin.catalog import Catalog
from models_cordis_plugin.named import (
    BUILT_IN,
    CLAUDE_CODE,
    OPENAI,
    ModelConfig,
    ModelsError,
    Named,
    chosen,
    combined,
    in_project,
    models_file,
    parsed,
    problem,
)
from models_cordis_plugin.providers import Unusable, known, opened, resolved
from models_cordis_plugin.switch import Switch, SwitchConfig, model_list
from models_cordis_plugin.wiring import CatalogConfig, catalog, model, set_model, shadowing, switch

__all__ = [
    "BUILT_IN",
    "CLAUDE_CODE",
    "OPENAI",
    "Catalog",
    "CatalogConfig",
    "ModelConfig",
    "ModelsError",
    "Named",
    "Switch",
    "SwitchConfig",
    "Unusable",
    "catalog",
    "chosen",
    "combined",
    "in_project",
    "known",
    "model",
    "model_list",
    "models_file",
    "opened",
    "parsed",
    "problem",
    "resolved",
    "set_model",
    "shadowing",
    "switch",
]
