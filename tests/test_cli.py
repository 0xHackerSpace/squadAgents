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


# --- the execution trace -----------------------------------------------------


def test_inspect_trace_prints_the_build_graph(capsys):
    from pathlib import Path

    tribe = Path(__file__).resolve().parent.parent / "tribe"
    if not tribe.is_dir():
        import pytest

        pytest.skip("tribe/ not present")

    assert main(["inspect", str(tribe / "manager"), "--trace"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "build     tribe/manager" in out
    assert "delegate  tribe/manager -> tribe/orq-infra" in out


def test_run_writes_a_trail_even_when_the_run_fails(minimal, tmp_path, capsys):
    """The failure is the event most worth having, so the trail must survive it."""
    from oaf.runtime import read_trail

    trilha = tmp_path / "t.jsonl"
    code = main([
        "run", str(minimal), "oi",
        "--harness", "dry-run", "--trace", str(trilha), "--correlation", "K",
    ])

    assert code == EXIT_FAILED  # dry-run refuses to execute
    assert trilha.is_file(), "the trail was not written"
    eventos = read_trail(trilha)
    assert eventos and all(e.correlacao == "K" for e in eventos)


def test_trail_reads_back_what_run_wrote(minimal, tmp_path, capsys):
    trilha = tmp_path / "t.jsonl"
    main(["run", str(minimal), "oi", "--harness", "dry-run",
          "--trace", str(trilha), "--correlation", "K"])
    capsys.readouterr()

    assert main(["trail", str(trilha)]) == EXIT_OK
    assert "K  (" in capsys.readouterr().out


def test_trail_filters_by_correlation(minimal, tmp_path, capsys):
    trilha = tmp_path / "t.jsonl"
    for cid in ("A", "B"):
        main(["run", str(minimal), "oi", "--harness", "dry-run",
              "--trace", str(trilha), "--correlation", cid])
    capsys.readouterr()

    assert main(["trail", str(trilha), "--correlation", "A"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "A  (" in out and "B  (" not in out


def test_trail_on_a_missing_file_fails(tmp_path, capsys):
    assert main(["trail", str(tmp_path / "nope.jsonl")]) == EXIT_FAILED
    assert "no trail at" in capsys.readouterr().err


def test_trail_on_an_unknown_correlation_fails(minimal, tmp_path, capsys):
    trilha = tmp_path / "t.jsonl"
    main(["run", str(minimal), "oi", "--harness", "dry-run",
          "--trace", str(trilha), "--correlation", "A"])
    capsys.readouterr()

    assert main(["trail", str(trilha), "--correlation", "Z"]) == EXIT_FAILED
    assert "no events for correlation" in capsys.readouterr().err


def test_a_closed_pipe_is_not_an_error(minimal, tmp_path, monkeypatch):
    """`oaf trail x | head` must not print a traceback over the user's output."""
    import io

    trilha = tmp_path / "t.jsonl"
    main(["run", str(minimal), "oi", "--harness", "dry-run", "--trace", str(trilha)])

    class PipeFechado(io.StringIO):
        def write(self, _):
            raise BrokenPipeError

    monkeypatch.setattr("sys.stdout", PipeFechado())
    monkeypatch.setattr("oaf.cli._silence_stdout", lambda: None)
    assert main(["trail", str(trilha)]) == EXIT_OK
