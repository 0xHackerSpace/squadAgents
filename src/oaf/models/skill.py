"""SKILL.md, per the AgentSkills.io specification the OAF spec adopts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import Str


class SkillMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    author: Str | None = None
    version: Str | None = None


class SkillManifest(BaseModel):
    """Only `name` and `description` are required by AgentSkills.io.

    The spec's example also shows `license`, `metadata` and `allowed-tools`, but
    the reference skills shipped with OpenHarness carry name and description
    alone, so everything else stays optional.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: Str
    description: Str
    license: Str | None = None
    metadata: SkillMetadata = Field(default_factory=SkillMetadata)
    allowed_tools: list[Str] = Field(default_factory=list, alias="allowed-tools")

    @property
    def version(self) -> str | None:
        return self.metadata.version


class SkillDocument(BaseModel):
    """A SKILL.md file plus the on-disk companions the spec allows."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    manifest: SkillManifest
    body: str
    #: False when the file carried no YAML frontmatter and the manifest was
    #: inferred from the directory name and the body's opening lines.
    frontmatter_present: bool = True
    #: Relative paths of files under resources/, scripts/ and assets/.
    resources: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.manifest.name
