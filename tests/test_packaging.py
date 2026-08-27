"""Packaging: the .zip round trip and the manifest dialects found in the wild."""

import zipfile

import pytest

from oaf.errors import ParseError
from oaf.models.package import PackageManifest
from oaf.packaging import build_package, extract_package, read_package


def test_round_trip_preserves_every_agent(fixtures, tmp_path):
    archive = build_package(
        fixtures / "valid", tmp_path / "acme-1.0.0.zip", name="acme", version="1.0.0"
    )
    names = zipfile.ZipFile(archive).namelist()
    assert "PACKAGE.yaml" in names
    assert "full-featured/skills/csv-report/SKILL.md" in names

    contents = extract_package(archive, tmp_path / "out")
    assert contents.manifest.dialect == "spec"
    assert len(contents.agent_dirs) == 3
    assert not contents.diagnostics.errors


def test_packaging_writes_the_spec_dialect(fixtures, tmp_path):
    archive = build_package(fixtures / "valid", tmp_path / "p.zip")
    manifest = extract_package(archive, tmp_path / "out").manifest
    assert manifest.format == "oaf-package"
    assert manifest.contents_mode == "bundled"


def test_spec_dialect_manifest_is_read():
    manifest = PackageManifest.model_validate(
        {
            "format": "oaf-package",
            "formatVersion": "1.0.0",
            "version": "1.0.0",
            "agents": [{"slug": "acme/x", "version": "1.0.0"}],
            "contents": {"mode": "referenced"},
        }
    )
    assert manifest.dialect == "spec"
    assert manifest.contents_mode == "referenced"
    assert manifest.agents[0].directory == "x"


def test_toolkit_dialect_manifest_is_read():
    """The shape the published travel-research package uses."""
    manifest = PackageManifest.model_validate(
        {
            "name": "Travel Research Toolkit",
            "version": "0.1.0",
            "agents": [{"slug": "trip-coordinator", "version": "0.1.0",
                        "path": "trip-coordinator/"}],
        }
    )
    assert manifest.dialect == "toolkit"
    assert manifest.agents[0].directory == "trip-coordinator"


def test_generated_dialect_manifest_is_read():
    """The shape inside the published sample zips: contents_mode, no slug."""
    manifest = PackageManifest.model_validate(
        {
            "name": "openharness-recipe-finder-package",
            "version": "0.1.0",
            "created_at": "2026-01-22T22:54:02Z",
            "contents_mode": "bundled",
            "agents": [{"path": "package/", "name": "Recipe Finder Agent",
                        "version": "0.1.0", "vendorKey": "openharness",
                        "agentKey": "recipe-finder"}],
        }
    )
    assert manifest.dialect == "generated"
    assert manifest.agents[0].canonical_slug == "openharness/recipe-finder"


def test_manifest_listing_a_missing_agent_is_an_error(fixtures, tmp_path):
    package = tmp_path / "pkg"
    (package / "minimal").mkdir(parents=True)
    (package / "minimal" / "AGENTS.md").write_text(
        (fixtures / "valid" / "minimal" / "AGENTS.md").read_text()
    )
    (package / "PACKAGE.yaml").write_text(
        'format: "oaf-package"\nversion: "1.0.0"\n'
        'agents:\n  - slug: "acme/ghost"\n    version: "1.0.0"\n'
    )
    contents = read_package(package)
    assert "package.missing-agent" in {d.code for d in contents.diagnostics.errors}


def test_packaging_an_empty_directory_is_refused(tmp_path):
    from oaf.errors import OafError

    (tmp_path / "empty").mkdir()
    with pytest.raises(OafError, match="no agent directory"):
        build_package(tmp_path / "empty", tmp_path / "out.zip")


def test_path_traversal_in_an_archive_is_refused(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.txt", "nope")
    with pytest.raises(ParseError, match="escapes the extraction directory"):
        extract_package(archive, tmp_path / "out")
