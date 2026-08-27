"""Invariants of the written documentation.

Documentation that lies is worse than documentation that is missing, because it
gets followed. Where a document makes a checkable claim about another file, the
check lives here.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADR = ROOT / "adr.md"
USE_CASE = ROOT / "docs" / "USE_CASE.md"
TRIBE = ROOT / "tribe" / "README.md"

MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)

#: Documents every reader is pointed at, and must therefore exist.
LINKED_DOCS = [
    ROOT / "README.md",
    ADR,
    ROOT / "docs" / "CONFORMANCE.md",
    ROOT / "docs" / "CLI.md",
    USE_CASE,
    TRIBE,
    ROOT / "docs" / "SDD.md",
    ROOT / "docs" / "PROMPTS.md",
    ROOT / "examples" / "agents" / "README.md",
]


def _slugify(heading: str) -> str:
    """GitHub's anchor rule: lowercase, punctuation dropped, each space a hyphen.

    Consecutive spaces are not collapsed — a heading with an em dash yields
    `adr-001--o-...` because dropping the dash leaves two spaces behind.
    """
    text = re.sub(r"[^\w\s-]", "", heading.strip().lower(), flags=re.UNICODE)
    return text.replace(" ", "-")


def _headings(text: str) -> set[str]:
    return {_slugify(m.group(1)) for m in re.finditer(r"^#{1,4}\s+(.+)$", text, re.M)}


def _diagrams(path: Path) -> list[str]:
    return [block.strip() for block in MERMAID.findall(path.read_text(encoding="utf-8"))]


@pytest.mark.parametrize("path", LINKED_DOCS, ids=lambda p: p.name)
def test_linked_document_exists(path: Path):
    assert path.is_file(), f"{path} is linked from the docs but missing"


def test_every_adr_is_in_the_index():
    text = ADR.read_text(encoding="utf-8")
    sections = re.findall(r"^## (ADR-\d+) — ", text, re.M)
    assert sections, "no ADR sections found"

    index = text.split("## 1. Contexto")[0]
    for number in sections:
        digits = number.split("-")[1]
        assert f"[{digits}](#" in index, f"{number} has no index entry"


def test_every_internal_anchor_resolves():
    """A broken anchor in the index is invisible until someone clicks it."""
    text = ADR.read_text(encoding="utf-8")
    headings = _headings(text)
    broken = [a for a in re.findall(r"\]\(#([^)]+)\)", text) if a not in headings]
    assert not broken, f"anchors with no matching heading: {broken}"


@pytest.mark.parametrize("source", [USE_CASE, TRIBE], ids=lambda p: p.parent.name)
def test_adr_carries_every_diagram_of_the_consumer_docs(source: Path):
    """adr.md is the single place that holds every flow diagram.

    Each consumer document keeps its own copy because it has to stand alone, so
    the copies must not drift from the record.
    """
    missing = [d for d in _diagrams(source) if d not in _diagrams(ADR)]
    assert not missing, (
        f"{len(missing)} diagram(s) in {source.name} are absent or altered in adr.md"
    )


def test_the_adr_diagrams_are_all_declared_mermaid():
    diagrams = _diagrams(ADR)
    assert len(diagrams) >= 17
    for diagram in diagrams:
        first = diagram.splitlines()[0].strip()
        assert first.startswith(
            ("flowchart", "sequenceDiagram", "classDiagram", "stateDiagram", "erDiagram")
        ), f"unrecognized diagram type: {first!r}"


def test_no_document_points_at_the_removed_placeholder_modules():
    """src/agents/ was deleted when the squad became real OAF agents."""
    for path in LINKED_DOCS:
        text = path.read_text(encoding="utf-8")
        assert "src/agents/agent_" not in text, f"{path.name} still references src/agents/"


# --- the SDD's one checkable claim -------------------------------------------

SDD = ROOT / "docs" / "SDD.md"


@pytest.mark.skipif(not SDD.is_file(), reason="docs/SDD.md not present")
def test_the_sdd_taxonomy_table_matches_the_validator():
    """The SDD states that underscores break OAF identity and hyphens do not.

    That claim is what its whole naming section rests on, so it is checked
    against the validator rather than trusted.
    """
    from oaf.models.common import is_canonical_slug, is_kebab_case

    assert not is_kebab_case("agent_orq_infra")
    assert is_kebab_case("agent-orq-infra")
    assert not is_canonical_slug("tribe/agent_orq_infra")
    assert is_canonical_slug("tribe/agent-orq-infra")

    text = SDD.read_text(encoding="utf-8")
    assert "identity.not-kebab-case" in text, "the SDD must name the diagnostic it would trigger"


@pytest.mark.skipif(not SDD.is_file(), reason="docs/SDD.md not present")
def test_the_sdd_derivation_rule_produces_the_names_it_shows():
    """destino = "agent-orq-" + categoria, for every category in the tribe."""
    import json

    schema = json.loads(
        (ROOT / "tribe" / "manager" / "skills" / "taxonomia" / "resources"
         / "triagem.schema.json").read_text(encoding="utf-8")
    )
    text = SDD.read_text(encoding="utf-8")
    acionaveis = [
        c for c in schema["properties"]["categoria"]["enum"] if c != "fora_de_escopo"
    ]
    for categoria in acionaveis:
        # The SDD's own example names must follow the rule it states.
        curto = {"infraestrutura": "infra"}.get(categoria, categoria)
        assert f"agent-orq-{curto}" in text, f"no orchestrator named for {categoria}"
        assert f"agent-coord-{curto}" in text, f"no coordinator named for {categoria}"
