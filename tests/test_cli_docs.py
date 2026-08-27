"""The CLI reference must not drift from the parser.

docs/CLI.md is written by hand, so nothing stops it from going stale when a flag
is added or renamed. These tests close that gap: every argument the parser
defines must explain itself in `--help` and must appear in the reference.
"""

import argparse
from pathlib import Path

import pytest

from oaf.cli import _build_parser

DOC = Path(__file__).resolve().parent.parent / "docs" / "CLI.md"

pytestmark = pytest.mark.skipif(not DOC.is_file(), reason="docs/CLI.md not present")


def _subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("the parser defines no subcommands")


def _arguments(parser: argparse.ArgumentParser) -> list[argparse.Action]:
    """Every argument of a subparser except the automatic -h."""
    return [a for a in parser._actions if not isinstance(a, argparse._HelpAction)]


@pytest.fixture(scope="module")
def parser():
    return _build_parser()


@pytest.fixture(scope="module")
def doc() -> str:
    return DOC.read_text(encoding="utf-8")


def test_every_subcommand_is_documented(parser, doc):
    for name in _subparsers(parser):
        assert f"## `oaf {name}`" in doc, f"docs/CLI.md has no section for {name!r}"


def test_every_argument_explains_itself_in_help(parser):
    """A flag whose --help says nothing is a flag nobody can use."""
    missing = [
        f"{command} {action.dest}"
        for command, sub in _subparsers(parser).items()
        for action in _arguments(sub)
        if not action.help
    ]
    assert not missing, f"arguments with no help text: {missing}"


def test_every_flag_appears_in_the_reference(parser, doc):
    missing = []
    for command, sub in _subparsers(parser).items():
        for action in _arguments(sub):
            for flag in action.option_strings:
                if flag not in doc:
                    missing.append(f"{command} {flag}")
    assert not missing, f"flags absent from docs/CLI.md: {missing}"


def test_every_positional_appears_in_the_reference(parser, doc):
    missing = []
    for command, sub in _subparsers(parser).items():
        for action in _arguments(sub):
            if action.option_strings:
                continue
            name = (action.metavar or action.dest).rstrip(".")
            if name not in doc:
                missing.append(f"{command} {name}")
    assert not missing, f"positionals absent from docs/CLI.md: {missing}"


def test_every_choice_appears_in_the_reference(parser, doc):
    """A documented flag with an undocumented value is still a gap."""
    missing = []
    for command, sub in _subparsers(parser).items():
        for action in _arguments(sub):
            for choice in action.choices or ():
                if str(choice) not in doc:
                    missing.append(f"{command} {action.dest}={choice}")
    assert not missing, f"choices absent from docs/CLI.md: {missing}"


def test_documented_defaults_match_the_parser(parser, doc):
    """Spot-check the defaults the reference states in prose."""
    subs = _subparsers(parser)
    defaults = {
        ("validate", "profile"): "lenient",
        ("inspect", "harness"): "dry-run",
        ("run", "harness"): "agno",
        ("package", "package_version"): "0.1.0",
        ("package", "mode"): "bundled",
    }
    for (command, dest), expected in defaults.items():
        action = next(a for a in _arguments(subs[command]) if a.dest == dest)
        assert action.default == expected, f"{command} --{dest} default changed"
        assert f"`{expected}`" in doc


def test_required_flags_are_marked_required_in_the_reference(parser, doc):
    for command, sub in _subparsers(parser).items():
        for action in _arguments(sub):
            if action.required and action.option_strings:
                # The reference marks these in bold in the argument table.
                assert "**obrigatório**" in doc, command


def test_exit_codes_are_documented(doc):
    from oaf.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE

    for code in (EXIT_OK, EXIT_FAILED, EXIT_USAGE):
        assert f"`{code}`" in doc
