"""PACKAGE.yaml, the manifest of a distributable `.zip` of agents.

Three shapes exist in the wild and all three are accepted:

  spec        format/formatVersion/version, agents[{slug, version}], contents.mode
  toolkit     name/version/description/author/license, agents[{slug, version, path}]
  generated   name/version/created_at/contents_mode, agents[{path, name, version,
              vendorKey, agentKey}]  (as produced for the published sample zips)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import Str

ContentsMode = Literal["bundled", "referenced"]

OAF_PACKAGE_FORMAT = "oaf-package"


class PackageAgentEntry(BaseModel):
    """One agent listed in a package manifest."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    slug: Str | None = None
    version: Str | None = None
    path: Str | None = None
    name: Str | None = None
    vendor_key: Str | None = Field(default=None, alias="vendorKey")
    agent_key: Str | None = Field(default=None, alias="agentKey")

    @property
    def directory(self) -> str:
        """Where the agent lives inside the archive.

        The spec's manifest has no `path`, so an entry without one falls back to
        the slug's last segment, matching the flat layout the spec describes.
        """
        if self.path:
            return self.path.rstrip("/")
        if self.slug:
            return self.slug.split("/")[-1]
        if self.agent_key:
            return self.agent_key
        return ""

    @property
    def canonical_slug(self) -> str | None:
        if self.vendor_key and self.agent_key:
            return f"{self.vendor_key}/{self.agent_key}"
        return self.slug


class PackageManifest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    format: Str | None = None
    format_version: Str | None = Field(default=None, alias="formatVersion")
    name: Str | None = None
    version: Str | None = None
    description: Str | None = None
    author: Str | None = None
    license: Str | None = None
    created_at: Str | None = None
    agents: list[PackageAgentEntry] = Field(default_factory=list)
    contents_mode: ContentsMode = "bundled"
    dialect: Literal["spec", "toolkit", "generated"] = "spec"

    @model_validator(mode="before")
    @classmethod
    def _normalize_dialect(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "contents" in data:
            contents = data.pop("contents") or {}
            if isinstance(contents, dict) and "mode" in contents:
                data.setdefault("contents_mode", contents["mode"])
            dialect = "spec"
        elif "contents_mode" in data or "created_at" in data:
            dialect = "generated"
        elif data.get("format") == OAF_PACKAGE_FORMAT:
            dialect = "spec"
        else:
            dialect = "toolkit"
        data["dialect"] = dialect
        return data
