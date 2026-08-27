"""Packing and unpacking OAF `.zip` distributions.

The spec's packaging section: a plain zip holding PACKAGE.yaml at the root plus
one directory per agent, stored flat, each self-contained. `contents.mode` says
whether well-known skills travel with the package (`bundled`) or are fetched at
install time (`referenced`).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..errors import DiagnosticBag, OafError, ParseError
from ..loader import AGENTS_MD, discover_agents, load_agent
from ..models.package import OAF_PACKAGE_FORMAT, ContentsMode, PackageManifest
from ..parse import PACKAGE_YAML, parse_package_manifest

#: Never carried into a distributable archive.
EXCLUDED_NAMES = {".git", ".venv", "__pycache__", ".DS_Store", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


@dataclass
class PackageContents:
    """An unpacked package: its manifest and the agent directories in it."""

    root: Path
    manifest: PackageManifest | None
    agent_dirs: list[Path] = field(default_factory=list)
    diagnostics: DiagnosticBag = field(default_factory=DiagnosticBag)


def _should_include(path: Path) -> bool:
    if any(part in EXCLUDED_NAMES for part in path.parts):
        return False
    return path.suffix not in EXCLUDED_SUFFIXES


def build_package(
    source: Path,
    output: Path,
    *,
    name: str | None = None,
    version: str = "0.1.0",
    mode: ContentsMode = "bundled",
) -> Path:
    """Pack every agent under `source` into an OAF `.zip` at `output`.

    The manifest written is the spec's own dialect: `format: oaf-package` with
    `contents.mode`. Reading stays permissive, writing stays canonical.
    """
    source = Path(source)
    output = Path(output)
    agent_dirs = discover_agents(source)
    if not agent_dirs:
        raise OafError(f"no agent directory (one containing {AGENTS_MD}) found under {source}")

    entries = []
    for directory in agent_dirs:
        agent = load_agent(directory)
        # Flat storage: each agent sits at the archive root under its own name.
        arc_name = directory.name if directory != source else agent.manifest.agent_key
        entries.append(
            {
                "slug": agent.manifest.canonical_slug,
                "version": agent.manifest.version,
                "path": f"{arc_name}/",
                "_dir": directory,
                "_arc": arc_name,
            }
        )

    manifest = {
        "format": OAF_PACKAGE_FORMAT,
        "formatVersion": "1.0.0",
        "name": name or source.name,
        "version": version,
        "agents": [
            {"slug": e["slug"], "version": e["version"], "path": e["path"]} for e in entries
        ],
        "contents": {"mode": mode},
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PACKAGE_YAML, yaml.safe_dump(manifest, sort_keys=False))
        for entry in entries:
            directory: Path = entry["_dir"]
            for path in sorted(directory.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(directory)
                if not _should_include(relative):
                    continue
                archive.write(path, f"{entry['_arc']}/{relative.as_posix()}")
    return output


def extract_package(archive_path: Path, destination: Path) -> PackageContents:
    """Extract an OAF `.zip` into `destination` and inventory what it holds."""
    archive_path = Path(archive_path)
    destination = Path(destination)
    if not zipfile.is_zipfile(archive_path):
        raise ParseError("not a zip archive", path=archive_path)

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            _guard_member(member.filename, archive_path)
        archive.extractall(destination)

    return read_package(destination)


def read_package(root: Path) -> PackageContents:
    """Inventory an already-unpacked package directory."""
    root = Path(root)
    contents = PackageContents(root=root, manifest=None)

    manifest_path = root / PACKAGE_YAML
    if manifest_path.is_file():
        try:
            contents.manifest = parse_package_manifest(manifest_path)
        except OafError as exc:
            contents.diagnostics.error("package.unparsable", str(exc), path=manifest_path)
    else:
        contents.diagnostics.warning(
            "package.no-manifest",
            f"no {PACKAGE_YAML} at the package root",
            path=root,
            hint="the spec requires PACKAGE.yaml alongside the agent directories",
        )

    contents.agent_dirs = discover_agents(root)
    if not contents.agent_dirs:
        contents.diagnostics.error(
            "package.no-agents",
            f"no directory containing {AGENTS_MD} was found",
            path=root,
        )

    _cross_check(contents)
    return contents


def _cross_check(contents: PackageContents) -> None:
    """Compare what the manifest claims against what is actually in the package."""
    manifest = contents.manifest
    if manifest is None:
        return

    on_disk = {}
    for directory in contents.agent_dirs:
        try:
            agent = load_agent(directory)
        except OafError as exc:
            contents.diagnostics.error("package.agent-unparsable", str(exc), path=directory)
            continue
        on_disk[agent.canonical_slug] = agent
        on_disk.setdefault(agent.slug, agent)

    for entry in manifest.agents:
        slug = entry.canonical_slug
        if slug and slug not in on_disk:
            contents.diagnostics.error(
                "package.missing-agent",
                f"{PACKAGE_YAML} lists {slug!r} but no such agent is in the package",
                path=contents.root / PACKAGE_YAML,
            )
            continue
        agent = on_disk.get(slug) if slug else None
        if agent and entry.version and entry.version != agent.manifest.version:
            contents.diagnostics.warning(
                "package.version-mismatch",
                f"{PACKAGE_YAML} lists {slug} at {entry.version} but the agent "
                f"declares {agent.manifest.version}",
                path=contents.root / PACKAGE_YAML,
            )

    listed = {e.canonical_slug for e in manifest.agents if e.canonical_slug}
    for directory in contents.agent_dirs:
        try:
            agent = load_agent(directory)
        except OafError:
            continue
        if listed and agent.canonical_slug not in listed and agent.slug not in listed:
            contents.diagnostics.warning(
                "package.unlisted-agent",
                f"{agent.canonical_slug} is in the package but not listed in {PACKAGE_YAML}",
                path=directory,
            )


def _guard_member(name: str, archive_path: Path) -> None:
    """Refuse absolute paths and `..` traversal in archive members."""
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ParseError(
            f"archive member {name!r} escapes the extraction directory",
            path=archive_path,
        )
