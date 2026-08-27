"""The CLI's exit codes and output contracts."""

import json

from oaf.cli import EXIT_FAILED, EXIT_OK, main


def test_validate_returns_zero_on_a_clean_tree(fixtures, capsys):
    assert main(["validate", str(fixtures / "valid"), "--profile", "strict"]) == EXIT_OK
    assert "3 agent(s) OK" in capsys.readouterr().out


def test_validate_returns_nonzero_on_a_cycle(fixtures, capsys):
    assert main(["validate", str(fixtures / "cycles")]) == EXIT_FAILED
    assert "agent.cycle" in capsys.readouterr().out


def test_validate_json_is_machine_readable(fixtures, capsys):
    main(["validate", str(fixtures / "valid"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile"] == "lenient"
    assert {a["slug"] for a in payload["agents"]} == {
        "acme/data-analyst", "acme/simple", "acme/code-reviewer"
    }


def test_validate_on_an_empty_directory_fails(tmp_path, capsys):
    assert main(["validate", str(tmp_path)]) == EXIT_FAILED
    assert "no agent found" in capsys.readouterr().err


def test_inspect_prints_the_resolved_definition(full_featured, capsys):
    assert main(["inspect", str(full_featured)]) == EXIT_OK
    out = capsys.readouterr().out
    assert "acme/data-analyst" in out
    assert "openai/gpt-5.2" in out


def test_inspect_json_carries_the_resolved_model(full_featured, capsys):
    main(["inspect", str(full_featured), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["resolvedModel"]["name"] == "gpt-5.2"
    assert payload["skills"][0]["status"] == "local"


def test_inspect_prompt_prints_the_system_prompt(full_featured, capsys):
    main(["inspect", str(full_featured), "--prompt"])
    assert "Available Skills" in capsys.readouterr().out


def test_package_and_unpack_round_trip(fixtures, tmp_path, capsys):
    archive = tmp_path / "p.zip"
    assert main(["package", str(fixtures / "valid"), "-o", str(archive)]) == EXIT_OK
    assert main(["unpack", str(archive), "-d", str(tmp_path / "out")]) == EXIT_OK
    assert "agent" in capsys.readouterr().out


def test_export_writes_files(full_featured, tmp_path, capsys):
    code = main(
        ["export", str(full_featured), "--target", "letta", "-d", str(tmp_path)]
    )
    assert code == EXIT_OK
    assert (tmp_path / "data-analyst.af").is_file()


def test_no_command_prints_help(capsys):
    from oaf.cli import EXIT_USAGE

    assert main([]) == EXIT_USAGE
    assert "usage" in capsys.readouterr().out.lower()
