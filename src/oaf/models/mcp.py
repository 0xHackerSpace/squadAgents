"""ActiveMCP.json and config.yaml.

Both files exist in two incompatible shapes: the one the spec documents and the
one the reference agents published alongside the spec actually use. Each model
below accepts either and exposes a single normalized view, so the rest of the
harness never branches on which dialect a file was written in.
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import Str

ContextStrategy = Literal["subset", "all"]

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value: str, *, environ: dict[str, str] | None = None) -> str:
    """Expand `${VAR}` references, which the spec allows in `auth.token`.

    An unset variable expands to the empty string rather than raising: whether a
    missing credential is fatal is the caller's decision, and the validator
    reports it as a diagnostic.
    """
    env = os.environ if environ is None else environ
    return _ENV_REF.sub(lambda m: env.get(m.group(1), ""), value)


def missing_env_refs(value: str, *, environ: dict[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    return [name for name in _ENV_REF.findall(value) if name not in env]


class SelectedTool(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Str
    enabled: bool = True
    description: Str | None = None
    required: bool = False


class ActiveMcp(BaseModel):
    """Tool subsetting for one MCP server.

    Spec dialect:  `selectedTools`, `excludedTools`, `contextStrategy`, `vendor`/`server`.
    Reference dialect: `enabled_tools`, `disabled_tools`, `tool_config`, `name`.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    vendor: Str | None = None
    server: Str | None = None
    version: Str | None = None
    description: Str | None = None
    selected_tools: list[SelectedTool] = Field(default_factory=list, alias="selectedTools")
    excluded_tools: list[Str] = Field(default_factory=list, alias="excludedTools")
    context_strategy: ContextStrategy = Field(default="subset", alias="contextStrategy")
    tool_config: dict[str, Any] = Field(default_factory=dict)
    #: Which dialect the source file was written in, for diagnostics.
    dialect: Literal["spec", "reference", "empty"] = "empty"

    @model_validator(mode="before")
    @classmethod
    def _normalize_dialect(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        spec_shaped = "selectedTools" in data or "excludedTools" in data
        ref_shaped = "enabled_tools" in data or "disabled_tools" in data
        if ref_shaped:
            data.setdefault("server", data.get("name"))
            data["selectedTools"] = [
                {"name": tool, "enabled": True}
                for tool in data.pop("enabled_tools", []) or []
            ] + list(data.pop("selectedTools", []) or [])
            data["excludedTools"] = list(data.pop("disabled_tools", []) or []) + list(
                data.pop("excludedTools", []) or []
            )
        data["dialect"] = "reference" if ref_shaped else ("spec" if spec_shaped else "empty")
        return data

    @property
    def enabled_tool_names(self) -> list[str]:
        return [t.name for t in self.selected_tools if t.enabled]

    @property
    def required_tool_names(self) -> list[str]:
        return [t.name for t in self.selected_tools if t.enabled and t.required]

    def permits(self, tool_name: str) -> bool:
        """Whether a tool advertised by the server should reach the agent.

        `excludedTools` entries ending in `*` are treated as prefix patterns:
        the reference agents use `admin.*`, which has no meaning as a literal
        tool name.
        """
        for pattern in self.excluded_tools:
            if pattern.endswith("*"):
                if tool_name.startswith(pattern[:-1]):
                    return False
            elif tool_name == pattern:
                return False
        if self.context_strategy == "all":
            return True
        return tool_name in self.enabled_tool_names


class McpConnection(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["sse", "http", "stdio"] = "http"
    url: Str | None = None
    command: Str | None = None
    args: list[Str] = Field(default_factory=list)
    timeout: int | None = None


class McpAuth(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Str | None = None
    token: Str | None = None
    header: Str | None = None
    env_var: Str | None = None

    def resolve_token(self, *, environ: dict[str, str] | None = None) -> str | None:
        """The concrete secret, from `${VAR}` in `token` or from `env_var`."""
        env = os.environ if environ is None else environ
        if self.token:
            return expand_env(self.token, environ=env) or None
        if self.env_var:
            return env.get(self.env_var) or None
        return None

    def unresolved_env(self, *, environ: dict[str, str] | None = None) -> list[str]:
        env = os.environ if environ is None else environ
        if self.token:
            return missing_env_refs(self.token, environ=env)
        if self.env_var and self.env_var not in env:
            return [self.env_var]
        return []


class McpConfig(BaseModel):
    """Connection, auth and limits for one MCP server.

    Spec dialect: top-level `vendor`/`server`/`version`, `auth`, `rate_limit`.
    Reference dialect: a `server:` mapping with `name`, plus `authentication`
    and `rate_limiting`.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    vendor: Str | None = None
    server: Str | None = None
    version: Str | None = None
    connection: McpConnection = Field(default_factory=McpConnection)
    auth: McpAuth | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)
    rate_limit: dict[str, Any] = Field(default_factory=dict)
    dialect: Literal["spec", "reference", "empty"] = "empty"

    @model_validator(mode="before")
    @classmethod
    def _normalize_dialect(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        dialect = "empty"
        # `server:` as a mapping is the reference dialect; as a string it is the spec's.
        server = data.get("server")
        if isinstance(server, dict):
            dialect = "reference"
            data["server"] = server.get("name")
            data.setdefault("vendor", server.get("vendor"))
        elif server is not None:
            dialect = "spec"
        if "authentication" in data:
            dialect = "reference"
            data.setdefault("auth", data.pop("authentication"))
        if "rate_limiting" in data:
            dialect = "reference"
            data.setdefault("rate_limit", data.pop("rate_limiting"))
        data["dialect"] = dialect
        return data
