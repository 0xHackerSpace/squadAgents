"""The `oaf` command line: validate, inspect, run, package, export.

Argparse rather than a CLI framework, so the harness stays installable with two
dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import OafError, Severity
from .export import EXPORTERS
from .loader import load_agent
from .packaging import build_package, extract_package
from .resolve import Workspace, resolve_agent
from .runtime import ADAPTERS, get_adapter
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
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("interrupted", file=sys.stderr)
        return EXIT_FAILED


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oaf",
        description="A harness for the Open Agent Format (OAF).",
    )
    parser.add_argument("--version", action="version", version=f"oaf {__version__}")
    sub = parser.add_subparsers(dest="command")

    validate = sub.add_parser("validate", help="check agents against the specification")
    validate.add_argument("path", type=Path, nargs="?", default=Path("."))
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
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--json", action="store_true")
    inspect.add_argument(
        "--prompt", action="store_true", help="print the composed system prompt"
    )
    inspect.add_argument("--harness", choices=sorted(ADAPTERS), default="dry-run")
    inspect.set_defaults(handler=_cmd_inspect)

    run = sub.add_parser("run", help="run an agent against a message")
    run.add_argument("path", type=Path)
    run.add_argument("message", nargs="+", help="the message to send")
    run.add_argument("--harness", choices=sorted(ADAPTERS), default="agno")
    run.add_argument("--model", help="override the model, as 'provider/name' or an alias")
    run.add_argument("--skills", choices=["eager", "progressive"], default=None)
    run.add_argument("--stream", action="store_true")
    run.set_defaults(handler=_cmd_run)

    package = sub.add_parser("package", help="pack agents into an OAF .zip")
    package.add_argument("path", type=Path)
    package.add_argument("-o", "--output", type=Path, required=True)
    package.add_argument("--name")
    package.add_argument("--package-version", default="0.1.0")
    package.add_argument("--mode", choices=["bundled", "referenced"], default="bundled")
    package.set_defaults(handler=_cmd_package)

    unpack = sub.add_parser("unpack", help="extract an OAF .zip and inspect it")
    unpack.add_argument("archive", type=Path)
    unpack.add_argument("-d", "--destination", type=Path, required=True)
    unpack.set_defaults(handler=_cmd_unpack)

    export = sub.add_parser("export", help="export an agent to a harness-native format")
    export.add_argument("path", type=Path)
    export.add_argument("--target", choices=sorted(EXPORTERS), required=True)
    export.add_argument("-d", "--destination", type=Path, required=True)
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

    adapter = get_adapter(args.harness, model_override=args.model, skill_mode=args.skills)
    built = adapter.build(resolved)
    for note in built.notes:
        print(f"note: {note}", file=sys.stderr)

    reply = adapter.run(built, " ".join(args.message), stream=args.stream)
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
