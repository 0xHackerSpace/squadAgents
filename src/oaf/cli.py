"""The `oaf` command line: validate, inspect, run, package, export.

Argparse rather than a CLI framework, so the harness stays installable with two
dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .errors import OafError, Severity
from .export import EXPORTERS
from .loader import load_agent
from .packaging import build_package, extract_package
from .resolve import Workspace, resolve_agent
from .runtime import ADAPTERS, Trace, get_adapter, group_by_correlation, read_trail
from .validate import Profile, validate_agent

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.handler(args)
    except OafError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILED
    except BrokenPipeError:
        # `oaf trail x | head` closes stdout early. That is not an error, and
        # letting it propagate prints a traceback over the user's output.
        # Redirect the stream so the interpreter's shutdown flush stays quiet.
        _silence_stdout()
        return EXIT_OK
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("interrupted", file=sys.stderr)
        return EXIT_FAILED


def _silence_stdout() -> None:
    """Point stdout at the void, so a closed pipe does not surface at exit."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, sys.stdout.fileno())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oaf",
        description="A harness for the Open Agent Format (OAF).",
        epilog="Every command takes a directory containing AGENTS.md, or a directory "
        "of them. See docs/CLI.md for the full reference.",
    )
    parser.add_argument("--version", action="version", version=f"oaf {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    validate = sub.add_parser("validate", help="check agents against the specification")
    validate.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path("."),
        metavar="PATH",
        help="agent directory, or a directory of them; every agent found is checked "
        "(default: the current directory)",
    )
    validate.add_argument(
        "--profile",
        choices=[p.value for p in Profile],
        default=Profile.LENIENT.value,
        help="strict enforces every rule as written; lenient (default) demotes the "
        "deviations the reference agents exhibit to warnings",
    )
    validate.add_argument("--json", action="store_true", help="emit diagnostics as JSON")
    validate.add_argument(
        "--quiet", action="store_true", help="print only errors, not warnings or notes"
    )
    validate.set_defaults(handler=_cmd_validate)

    inspect = sub.add_parser("inspect", help="print an agent's fully resolved definition")
    inspect.add_argument(
        "path",
        type=Path,
        metavar="PATH",
        help="the agent directory to inspect; its siblings become the workspace, so "
        "sub-agent references resolve",
    )
    inspect.add_argument(
        "--json", action="store_true", help="emit the resolved definition as JSON"
    )
    inspect.add_argument(
        "--prompt",
        action="store_true",
        help="print the composed system prompt instead of the summary",
    )
    inspect.add_argument(
        "--harness",
        choices=sorted(ADAPTERS),
        default="dry-run",
        help="which adapter resolves the model (default: dry-run, which needs no "
        "API key and instantiates no client)",
    )
    inspect.add_argument(
        "--trace",
        action="store_true",
        help="print the build trace — every agent and delegation edge, in the "
        "order the harness wires them — instead of the summary",
    )
    inspect.set_defaults(handler=_cmd_inspect)

    run = sub.add_parser("run", help="run an agent against a message")
    run.add_argument(
        "path",
        type=Path,
        metavar="PATH",
        help="the agent directory to run; its siblings become the workspace, so "
        "sub-agent references resolve",
    )
    run.add_argument(
        "message", nargs="+", metavar="MESSAGE", help="the message to send; multiple "
        "words are joined with spaces"
    )
    run.add_argument(
        "--harness",
        choices=sorted(ADAPTERS),
        default="agno",
        help="the backend to run on (default: agno; dry-run builds but refuses to "
        "execute)",
    )
    run.add_argument(
        "--model",
        metavar="MODEL",
        help="override the model for every agent in this run, as 'provider/name' or "
        "an alias; beats the manifest and the environment",
    )
    run.add_argument(
        "--skills",
        choices=["eager", "progressive"],
        default=None,
        help="how local skills reach the agent: progressive lists them and adds a "
        "load_skill tool, eager inlines every body into the prompt "
        "(default: whatever harnessConfig asks for, else progressive)",
    )
    run.add_argument(
        "--stream",
        action="store_true",
        help="stream the reply to the terminal as it is produced",
    )
    run.add_argument(
        "--trace",
        type=Path,
        metavar="FILE",
        help="append an execution trace to FILE as JSON lines; records every "
        "agent built, every delegation edge wired, and the run's outcome",
    )
    run.add_argument(
        "--correlation",
        metavar="ID",
        help="correlation id for this run (default: a fresh one); pass your own "
        "to tie the trace to a request you already track",
    )
    run.set_defaults(handler=_cmd_run)

    package = sub.add_parser("package", help="pack agents into an OAF .zip")
    package.add_argument(
        "path",
        type=Path,
        metavar="PATH",
        help="directory holding the agents to pack; every agent found is included",
    )
    package.add_argument(
        "-o", "--output", type=Path, required=True, metavar="FILE",
        help="the .zip file to write (required)",
    )
    package.add_argument(
        "--name",
        metavar="NAME",
        help="package name recorded in PACKAGE.yaml (default: the source directory's name)",
    )
    package.add_argument(
        "--package-version",
        default="0.1.0",
        metavar="VERSION",
        help="package version recorded in PACKAGE.yaml (default: 0.1.0); this is the "
        "package's version, not any agent's",
    )
    package.add_argument(
        "--mode",
        choices=["bundled", "referenced"],
        default="bundled",
        help="contents.mode in PACKAGE.yaml: bundled is self-contained, referenced "
        "expects well-known skills to be fetched at install time (default: bundled)",
    )
    package.set_defaults(handler=_cmd_package)

    unpack = sub.add_parser("unpack", help="extract an OAF .zip and inspect it")
    unpack.add_argument(
        "archive", type=Path, metavar="ARCHIVE", help="the .zip file to extract"
    )
    unpack.add_argument(
        "-d", "--destination", type=Path, required=True, metavar="DIR",
        help="directory to extract into; created if absent (required)",
    )
    unpack.set_defaults(handler=_cmd_unpack)

    trail = sub.add_parser("trail", help="read an execution trail written by `run --trace`")
    trail.add_argument(
        "file", type=Path, metavar="FILE", help="the JSON-lines trail to read"
    )
    trail.add_argument(
        "--correlation",
        metavar="ID",
        help="show only this request's events (default: every request in the file)",
    )
    trail.add_argument("--json", action="store_true", help="emit the events as JSON")
    trail.set_defaults(handler=_cmd_trail)

    export = sub.add_parser("export", help="export an agent to a harness-native format")
    export.add_argument(
        "path", type=Path, metavar="PATH", help="the agent directory to export"
    )
    export.add_argument(
        "--target",
        choices=sorted(EXPORTERS),
        required=True,
        help="the harness format to write (required); each is lossy in its own way "
        "and reports what it could not carry",
    )
    export.add_argument(
        "-d", "--destination", type=Path, required=True, metavar="DIR",
        help="directory to write into; the layout beneath it is the target's "
        "convention (required)",
    )
    export.set_defaults(handler=_cmd_export)

    return parser


# --- commands ---------------------------------------------------------------


def _cmd_validate(args) -> int:
    profile = Profile(args.profile)
    workspace = Workspace.from_path(args.path)
    if not workspace.agents:
        print(f"error: no agent found under {args.path}", file=sys.stderr)
        return EXIT_FAILED

    payload = []
    failures = 0
    for agent in workspace.agents:
        bag = validate_agent(agent, profile=profile)
        resolved = resolve_agent(agent, workspace=workspace)
        bag.extend(resolved.diagnostics)
        if not bag.ok:
            failures += 1
        if args.json:
            payload.append(
                {
                    "slug": agent.canonical_slug,
                    "root": str(agent.root),
                    "ok": bag.ok,
                    "diagnostics": [
                        {
                            "severity": d.severity.value,
                            "code": d.code,
                            "message": d.message,
                            "path": str(d.path) if d.path else None,
                            "line": d.line,
                            "field": d.field,
                        }
                        for d in bag
                    ],
                }
            )
        else:
            _print_report(agent, bag, quiet=args.quiet, root=args.path)

    if args.json:
        print(json.dumps({"profile": profile.value, "agents": payload}, indent=2))
    elif failures:
        print(f"\n{failures} of {len(workspace.agents)} agent(s) failed", file=sys.stderr)
    else:
        print(f"\n{len(workspace.agents)} agent(s) OK ({profile.value} profile)")
    return EXIT_FAILED if failures else EXIT_OK


def _print_report(agent, bag, *, quiet: bool, root: Path) -> None:
    status = "OK" if bag.ok else "FAILED"
    print(f"\n{agent.canonical_slug} v{agent.manifest.version} — {status}")
    for diagnostic in bag:
        if quiet and diagnostic.severity is not Severity.ERROR:
            continue
        print("  " + diagnostic.format(relative_to=root).replace("\n", "\n  "))


def _cmd_inspect(args) -> int:
    agent = load_agent(args.path)
    workspace = Workspace.from_path(args.path.parent if args.path.is_dir() else args.path)
    workspace.add(agent)
    resolved = resolve_agent(agent, workspace=workspace)
    built = get_adapter(args.harness).build(resolved) if args.harness == "dry-run" else None

    if args.prompt:
        from .runtime.prompt import build_system_prompt

        print(build_system_prompt(resolved))
        return EXIT_OK

    if args.trace:
        trace = Trace()
        adapter = get_adapter("dry-run", trace=trace)
        adapter.build(resolved)
        print(trace.format())
        return EXIT_OK

    summary = resolved.summary()
    if built is not None:
        summary["resolvedModel"] = {
            "provider": built.model.provider,
            "name": built.model.name,
            "origin": built.model.origin,
        }
        summary["skillMode"] = built.skill_mode

    if args.json:
        print(json.dumps(summary, indent=2))
        return EXIT_OK

    _print_summary(summary, resolved)
    return EXIT_OK


def _print_summary(summary: dict, resolved) -> None:
    print(f"{summary['name']}  ({summary['canonicalSlug']} v{summary['version']})")
    print(f"  root         {summary['root']}")
    print(f"  instructions {summary['instructionFormat']}")
    model = summary.get("resolvedModel")
    if model:
        print(f"  model        {model['provider']}/{model['name']}  [{model['origin']}]")
    if summary["tools"]:
        print(f"  tools        {', '.join(summary['tools'])}")
    for label, key, render in (
        ("skills", "skills", lambda s: f"{s['name']} [{s['status']}]"),
        ("mcp", "mcpServers", lambda s: f"{s['server']} [{s['status']}] {', '.join(s['tools'])}"),
        ("agents", "subAgents", lambda s: f"{s['slug']} [{s['status']}] {s['role'] or ''}"),
        ("packs", "packs", lambda s: f"{s['vendor']}/{s['pack']}"),
        ("weblets", "weblets", lambda s: f"{s['vendor']}/{s['weblet']} ({s['launch']})"),
    ):
        items = summary.get(key) or []
        for index, item in enumerate(items):
            prefix = f"  {label:12}" if index == 0 else " " * 14
            print(f"{prefix} {render(item)}")
    for diagnostic in resolved.diagnostics:
        print("  ! " + diagnostic.format().replace("\n", "\n    "))


def _cmd_run(args) -> int:
    agent = load_agent(args.path)
    workspace = Workspace.from_path(args.path.parent if args.path.is_dir() else args.path)
    workspace.add(agent)
    resolved = resolve_agent(agent, workspace=workspace)

    bag = validate_agent(agent, profile=Profile.LENIENT)
    if not bag.ok:
        for diagnostic in bag.errors:
            print(diagnostic.format(), file=sys.stderr)
        print("error: agent failed lenient validation; refusing to run", file=sys.stderr)
        return EXIT_FAILED

    trace = Trace(correlacao=args.correlation) if args.correlation else Trace()
    adapter = get_adapter(
        args.harness,
        model_override=args.model,
        skill_mode=args.skills,
        trace=trace if args.trace else None,
    )
    built = adapter.build(resolved)
    for note in built.notes:
        print(f"note: {note}", file=sys.stderr)

    try:
        reply = adapter.run(built, " ".join(args.message), stream=args.stream)
    finally:
        # The trail is written even when the run failed — a failure is the
        # event most worth having.
        if args.trace:
            trace.write(args.trace)
            print(f"trace: {len(trace)} events -> {args.trace}", file=sys.stderr)
    if reply:
        print(reply)
    return EXIT_OK


def _cmd_package(args) -> int:
    output = build_package(
        args.path,
        args.output,
        name=args.name,
        version=args.package_version,
        mode=args.mode,
    )
    print(f"wrote {output}")
    return EXIT_OK


def _cmd_unpack(args) -> int:
    contents = extract_package(args.archive, args.destination)
    manifest = contents.manifest
    if manifest is not None:
        print(f"package {manifest.name or '(unnamed)'} v{manifest.version or '?'} "
              f"[{manifest.dialect} dialect, {manifest.contents_mode}]")
    for directory in contents.agent_dirs:
        print(f"  agent {directory.relative_to(contents.root)}")
    for diagnostic in contents.diagnostics:
        print("  " + diagnostic.format(relative_to=contents.root), file=sys.stderr)
    return EXIT_FAILED if contents.diagnostics.errors else EXIT_OK


def _cmd_trail(args) -> int:
    if not args.file.is_file():
        print(f"error: no trail at {args.file}", file=sys.stderr)
        return EXIT_FAILED

    events = read_trail(args.file)
    por_pedido = group_by_correlation(events)
    if args.correlation:
        por_pedido = {k: v for k, v in por_pedido.items() if k == args.correlation}
        if not por_pedido:
            print(f"error: no events for correlation {args.correlation}", file=sys.stderr)
            return EXIT_FAILED

    if args.json:
        print(json.dumps(
            {k: [e.to_dict() for e in v] for k, v in por_pedido.items()}, indent=2
        ))
        return EXIT_OK

    for correlacao, sequencia in por_pedido.items():
        falhou = any(e.kind == "error" for e in sequencia)
        print(f"\n{correlacao}  ({len(sequencia)} events{', FAILED' if falhou else ''})")
        for event in sequencia:
            print("  " + event.format())
    return EXIT_OK


def _cmd_export(args) -> int:
    agent = load_agent(args.path)
    workspace = Workspace.from_path(args.path.parent if args.path.is_dir() else args.path)
    workspace.add(agent)
    resolved = resolve_agent(agent, workspace=workspace)

    result = EXPORTERS[args.target](resolved, args.destination)
    print(f"exported {resolved.slug} to {args.target}")
    for path in result.files:
        print(f"  {path}")
    for note in result.notes:
        print(f"  note: {note}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
