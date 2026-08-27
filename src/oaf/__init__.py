"""A harness for the Open Agent Format (OAF).

Implements OAF 0.8.0: parses the file formats the spec defines, validates against
its rules, resolves composition, and runs the result on a pluggable harness
backend.

    from oaf import load_agent, resolve_agent, validate_agent

    agent = load_agent("./my-agent")
    report = validate_agent(agent)
    resolved = resolve_agent(agent)
"""

from .errors import (
    Diagnostic,
    DiagnosticBag,
    HarnessError,
    OafError,
    ParseError,
    Severity,
)
from .loader import LoadedAgent, discover_agents, is_agent_dir, load_agent
from .resolve import ResolvedAgent, Workspace, resolve_agent, resolve_path
from .validate import Profile, validate_agent

#: The version of this harness.
__version__ = "0.1.0"

#: The version of the Open Agent Format specification it implements.
OAF_SPEC_VERSION = "0.8.0"

__all__ = [
    "__version__", "OAF_SPEC_VERSION",
    "load_agent", "discover_agents", "is_agent_dir", "LoadedAgent",
    "resolve_agent", "resolve_path", "ResolvedAgent", "Workspace",
    "validate_agent", "Profile",
    "OafError", "ParseError", "HarnessError",
    "Diagnostic", "DiagnosticBag", "Severity",
]
