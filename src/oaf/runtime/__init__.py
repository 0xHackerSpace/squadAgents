"""Harness backends that turn a resolved OAF agent into something runnable."""

from .agno_adapter import AgnoAdapter
from .base import BuildResult, DryRunAdapter, HarnessAdapter
from .models import DEFAULT_ALIASES, ResolvedModel, resolve_model
from .prompt import build_system_prompt, skill_mode_for

ADAPTERS: dict[str, type[HarnessAdapter]] = {
    "dry-run": DryRunAdapter,
    "agno": AgnoAdapter,
}


def get_adapter(name: str, **kwargs) -> HarnessAdapter:
    """Instantiate the adapter registered under `name`."""
    try:
        cls = ADAPTERS[name]
    except KeyError:
        known = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"unknown harness {name!r}; available: {known}") from None
    return cls(**kwargs)


__all__ = [
    "ADAPTERS", "get_adapter",
    "HarnessAdapter", "DryRunAdapter", "AgnoAdapter", "BuildResult",
    "ResolvedModel", "resolve_model", "DEFAULT_ALIASES",
    "build_system_prompt", "skill_mode_for",
]
