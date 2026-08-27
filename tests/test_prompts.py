"""docs/PROMPTS.md is generated, so it can drift from the agents it describes.

These tests regenerate it and compare, and hold the generator to the claims the
document itself makes about how an OAF prompt is composed.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TRIBE = ROOT / "tribe"
DOC = ROOT / "docs" / "PROMPTS.md"

sys.path.insert(0, str(ROOT / "examples"))

pytestmark = pytest.mark.skipif(not TRIBE.is_dir(), reason="tribe/ not present")


@pytest.fixture(scope="module")
def gerado():
    from dump_prompts import gerar

    return gerar(TRIBE)


@pytest.fixture(scope="module")
def comprometido():
    if not DOC.is_file():
        pytest.skip("docs/PROMPTS.md not present")
    return DOC.read_text(encoding="utf-8")


def test_the_committed_document_is_current(gerado, comprometido):
    """Regenerating must produce exactly what is committed.

    If this fails, an agent changed and the document did not:
        python examples/dump_prompts.py
    """
    assert gerado == comprometido, "docs/PROMPTS.md is stale — regenerate it"


def test_every_agent_has_a_section(gerado):
    from oaf.resolve import Workspace

    for agent in Workspace.from_path(TRIBE).agents:
        assert f"## {agent.canonical_slug}\n" in gerado, agent.canonical_slug


def test_every_index_anchor_resolves(gerado):
    """A broken anchor in a fourteen-entry index is invisible until clicked."""
    import re

    def slugify(heading: str) -> str:
        texto = re.sub(r"[^\w\s-]", "", heading.strip().lower(), flags=re.UNICODE)
        return texto.replace(" ", "-")

    headings = {slugify(m.group(1)) for m in re.finditer(r"^#{1,4}\s+(.+)$", gerado, re.M)}
    quebrados = [a for a in re.findall(r"\]\(#([^)]+)\)", gerado) if a not in headings]
    assert not quebrados, f"anchors with no matching heading: {quebrados}"


def test_the_authored_and_generated_halves_are_separated(gerado):
    """The document's whole claim is that a prompt has two origins."""
    assert gerado.count("### Corpo autorado") == gerado.count("### Composto pelo harness")
    assert gerado.count("### Corpo autorado") == 14


def test_the_authored_half_is_the_agents_body(gerado):
    """Not a paraphrase: the authored half must be the file's own body."""
    from oaf.loader import load_agent
    from oaf.resolve import resolve_agent

    resolvido = resolve_agent(load_agent(TRIBE / "manager"))
    corpo = resolvido.document.system_prompt.strip()
    assert corpo in gerado
    # And it must start where the file starts, not mid-document.
    assert corpo.startswith("# Propósito")


def test_the_generated_half_holds_only_harness_sections(gerado):
    """Anything else in that half would mean the split is wrong."""
    import re

    from dump_prompts import GERADAS

    blocos = re.findall(
        r"### Composto pelo harness\n\n````markdown\n(.*?)\n````", gerado, re.S
    )
    assert blocos
    for bloco in blocos:
        for linha in bloco.splitlines():
            if linha.startswith("## "):
                assert linha in GERADAS, f"unexpected generated section: {linha!r}"


def test_a_skill_body_never_reaches_the_prompt(gerado):
    """Progressive disclosure, asserted on the document that claims it."""
    corpo_da_skill = (
        TRIBE / "manager" / "skills" / "taxonomia" / "SKILL.md"
    ).read_text(encoding="utf-8")
    sonda = "Fronteiras que confundem"  # exists only in the skill body

    assert sonda in corpo_da_skill
    assert sonda not in gerado, "a skill body leaked into a composed prompt"


def test_the_index_reports_the_real_prompt_size(gerado):
    """A size that drifts makes the index worse than no index."""
    import re

    from oaf.loader import load_agent
    from oaf.resolve import Workspace, resolve_agent
    from oaf.runtime import build_system_prompt

    workspace = Workspace.from_path(TRIBE)
    real = len(build_system_prompt(
        resolve_agent(load_agent(TRIBE / "manager"), workspace=workspace)
    ))
    linha = re.search(r"\| \[`tribe/manager`\].*?\| (\d+) chars", gerado)
    assert linha and int(linha.group(1)) == real


def test_regenerating_is_deterministic():
    """Two runs must agree, or the drift test is noise."""
    from dump_prompts import gerar

    assert gerar(TRIBE) == gerar(TRIBE)
