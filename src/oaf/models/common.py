"""Scalar types the OAF spec constrains: semver, kebab-case keys, slugs, SPDX.

The spec states the constraints in prose ("kebab-case", "semantic version",
"SPDX license identifier") without a machine-readable schema, so they are
encoded once here and reused by every model.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator

# Official semver.org regex (https://semver.org/#is-there-a-suggested-regular-expression-regex-to-check-a-semver-string)
SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# A constraint is a bare version or a npm/pep-style range. The spec says
# "Semantic version or version constraint" for skills but never defines the
# constraint grammar, so the harness accepts the common operators and treats
# anything else as a diagnostic rather than a parse failure.
CONSTRAINT_RE = re.compile(r"^\s*(?:[\^~]|[<>]=?|=)?\s*\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.-]+)?\s*$")

KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*/[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_semver(value: str) -> bool:
    return bool(SEMVER_RE.match(value.strip()))


def is_version_constraint(value: str) -> bool:
    value = value.strip()
    return is_semver(value) or bool(CONSTRAINT_RE.match(value)) or value in {"*", "latest"}


def is_kebab_case(value: str) -> bool:
    return bool(KEBAB_RE.match(value))


def is_canonical_slug(value: str) -> bool:
    """A canonical slug is `vendorKey/agentKey` per the Identity Fields table."""
    return bool(SLUG_RE.match(value))


def _stringify(value: object) -> object:
    """YAML turns `version: 1.0` into a float and `0.1.0` into a string.

    Numbers are coerced back to text so the semver check sees what the author
    typed rather than a float repr.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return value


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


Str = Annotated[str, BeforeValidator(_stringify), BeforeValidator(_strip)]


def _must_be_semver(value: str) -> str:
    if not is_semver(value):
        raise ValueError(
            f"{value!r} is not a semantic version (expected MAJOR.MINOR.PATCH, e.g. '1.0.0')"
        )
    return value


VersionStr = Annotated[Str, AfterValidator(_must_be_semver)]

# SPDX identifiers seen in practice. The full list is ~600 entries; the harness
# only warns on unknown ones, so this is a recognition set and not a gate.
COMMON_SPDX = frozenset(
    {
        "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "MPL-2.0",
        "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
        "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
        "AGPL-3.0-only", "AGPL-3.0-or-later", "Unlicense", "CC0-1.0",
        "CC-BY-4.0", "CC-BY-SA-4.0", "Zlib", "Artistic-2.0", "EPL-2.0",
        "BSL-1.0", "PostgreSQL", "OFL-1.1", "NCSA", "Python-2.0", "WTFPL",
        "proprietary", "LicenseRef-Proprietary",
    }
)
