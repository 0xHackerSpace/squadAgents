"""Mapping an OAF `model:` field onto a concrete provider model.

The spec defines three aliases — "sonnet", "opus", "haiku" — as "latest" of each
Claude tier, and an object form carrying an explicit provider and name. "Latest"
moves, so the alias table is data rather than logic: override an entry through
the environment (`OAF_MODEL_SONNET=...`) or by passing your own table, without
touching this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from ..models.agent import AgentManifest

#: What each spec alias resolves to by default.
DEFAULT_ALIASES: dict[str, tuple[str, str]] = {
    "opus": ("anthropic", "claude-opus-5"),
    "sonnet": ("anthropic", "claude-sonnet-5"),
    "haiku": ("anthropic", "claude-haiku-4-5-20251001"),
}

#: Used when a manifest declares no model at all.
DEFAULT_MODEL = ("anthropic", "claude-sonnet-5")


@dataclass(frozen=True)
class ResolvedModel:
    """A provider and model name the runtime can actually instantiate."""

    provider: str
    name: str
    embedding: str | None = None
    #: How this was arrived at, for `oaf inspect` and for diagnostics.
    origin: str = "default"

    def __str__(self) -> str:
        return f"{self.provider}/{self.name}"


def resolve_model(
    manifest: AgentManifest,
    *,
    aliases: dict[str, tuple[str, str]] | None = None,
    environ: dict[str, str] | None = None,
    override: str | None = None,
) -> ResolvedModel:
    """Resolve `manifest.model` to a concrete provider/name pair.

    `override` wins over everything, so a caller can run any agent on any model
    without editing its AGENTS.md. It accepts "provider/name" or a bare alias.
    """
    env = os.environ if environ is None else environ
    table = _alias_table(aliases, env)

    if override:
        provider, name = _split_override(override, table)
        return ResolvedModel(provider, name, origin="override")

    spec = manifest.model_spec
    if spec is not None and spec.name:
        return ResolvedModel(
            provider=spec.provider or _infer_provider(spec.name),
            name=spec.name,
            embedding=spec.embedding,
            origin="manifest.model",
        )

    alias = manifest.model_alias
    if alias:
        if alias in table:
            provider, name = table[alias]
            return ResolvedModel(provider, name, origin=f"alias:{alias}")
        # An unrecognized string is taken at face value: it may well be a real
        # model id the author typed directly. The validator warns about it.
        return ResolvedModel(_infer_provider(alias), alias, origin="alias:literal")

    provider, name = DEFAULT_MODEL
    return ResolvedModel(provider, name, origin="default")


def _alias_table(
    aliases: dict[str, tuple[str, str]] | None, env: dict[str, str]
) -> dict[str, tuple[str, str]]:
    table = dict(DEFAULT_ALIASES if aliases is None else aliases)
    for alias in list(table):
        value = env.get(f"OAF_MODEL_{alias.upper()}")
        if value:
            table[alias] = _split_override(value, table)
    return table


def _split_override(value: str, table: dict[str, tuple[str, str]]) -> tuple[str, str]:
    value = value.strip()
    if value in table:
        return table[value]
    if "/" in value:
        provider, _, name = value.partition("/")
        return provider.strip(), name.strip()
    return _infer_provider(value), value


def _infer_provider(name: str) -> str:
    """Guess a provider from a model name when none was given."""
    lowered = name.lower()
    if lowered.startswith("claude"):
        return "anthropic"
    if lowered.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if lowered.startswith("gemini"):
        return "google"
    if lowered.startswith(("llama", "mistral", "mixtral", "qwen", "deepseek")):
        return "ollama"
    return "openai"
