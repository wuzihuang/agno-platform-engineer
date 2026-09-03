#!/usr/bin/env python3
"""Validate an Agent Skill directory without third-party dependencies."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ALLOWED_FRONTMATTER_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PATH_REFERENCE_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:references|templates|scripts)/[A-Za-z0-9_./{}-]+)"
)


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def parse_frontmatter(text: str, validation: Validation) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        validation.error("SKILL.md must start with YAML frontmatter delimiter '---'")
        return {}, text

    try:
        closing = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration:
        validation.error("SKILL.md frontmatter has no closing '---'")
        return {}, text

    fields: dict[str, str] = {}
    for number, line in enumerate(lines[1:closing], start=2):
        if not line.strip() or line.lstrip().startswith("#") or line.startswith((" ", "\t")):
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not match:
            validation.error(f"Invalid top-level frontmatter syntax at line {number}: {line!r}")
            continue
        key, value = match.group(1), (match.group(2) or "").strip()
        if key in fields:
            validation.error(f"Duplicate frontmatter field: {key}")
        fields[key] = value.strip('"\'')

    body = "\n".join(lines[closing + 1 :])
    return fields, body


def validate_frontmatter(root: Path, fields: dict[str, str], validation: Validation) -> None:
    unknown = sorted(set(fields) - ALLOWED_FRONTMATTER_FIELDS)
    if unknown:
        validation.error(f"Unknown top-level frontmatter field(s): {', '.join(unknown)}")

    name = fields.get("name", "")
    description = fields.get("description", "")

    if not name:
        validation.error("Frontmatter field 'name' is required")
    elif not NAME_RE.fullmatch(name):
        validation.error("name must contain lowercase letters/numbers separated by single hyphens")
    elif len(name) > 64:
        validation.error("name must be at most 64 characters")
    elif root.name != name:
        validation.error(f"Directory name {root.name!r} must match Skill name {name!r}")

    if not description:
        validation.error("Frontmatter field 'description' is required")
    elif len(description) > 1024:
        validation.error("description must be at most 1024 characters")
    elif "<" in description or ">" in description:
        validation.warn("description contains angle brackets; keep trigger text plain")

    compatibility = fields.get("compatibility", "")
    if len(compatibility) > 500:
        validation.error("compatibility must be at most 500 characters")


def validate_structure(root: Path, skill_text: str, body: str, validation: Validation) -> None:
    line_count = skill_text.count("\n") + 1
    word_count = len(re.findall(r"\S+", body))
    if line_count > 500:
        validation.warn(f"SKILL.md has {line_count} lines; progressive-disclosure guidance recommends <= 500")
    if word_count > 5000:
        validation.warn(f"SKILL.md has approximately {word_count} words/tokens; move detail into references")

    for required in ("README.md", "SOURCES.md"):
        if not (root / required).exists():
            validation.warn(f"Recommended file is missing: {required}")

    for directory in ("references", "templates", "scripts"):
        path = root / directory
        if not path.is_dir():
            validation.error(f"Expected directory is missing: {directory}/")

    references = sorted(set(PATH_REFERENCE_RE.findall(skill_text)))
    for relative in references:
        if "{" in relative or "}" in relative:
            continue
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            validation.error(f"Referenced path escapes the Skill root: {relative}")
            continue
        if not candidate.exists():
            validation.error(f"Referenced path does not exist: {relative}")


def validate_files(root: Path, validation: Validation) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                validation.error(f"Symlink escapes Skill root: {path.relative_to(root)}")
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        size = path.stat().st_size
        if size > 2_000_000:
            validation.warn(f"Large file ({size} bytes): {relative}")
        if path.suffix == ".py":
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, str(path), "exec")
            except (UnicodeDecodeError, SyntaxError) as exc:
                validation.error(f"Python syntax/encoding error in {relative}: {exc}")
        if relative.parts and relative.parts[0] == "scripts" and path.suffix == ".py":
            first_line = path.read_text(encoding="utf-8").splitlines()[:1]
            if not first_line or not first_line[0].startswith("#!"):
                validation.warn(f"Executable script has no shebang: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="Skill directory")
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    validation = Validation()

    skill_file = root / "SKILL.md"
    if not skill_file.is_file():
        print(f"ERROR: {skill_file} does not exist", file=sys.stderr)
        return 1

    try:
        skill_text = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        print(f"ERROR: SKILL.md must be UTF-8: {exc}", file=sys.stderr)
        return 1

    fields, body = parse_frontmatter(skill_text, validation)
    validate_frontmatter(root, fields, validation)
    validate_structure(root, skill_text, body, validation)
    validate_files(root, validation)

    for warning in validation.warnings:
        print(f"WARNING: {warning}")
    for error in validation.errors:
        print(f"ERROR: {error}", file=sys.stderr)

    print(
        f"Checked {root}: {len(validation.errors)} error(s), "
        f"{len(validation.warnings)} warning(s)"
    )
    if validation.errors or (args.warnings_as_errors and validation.warnings):
        return 1
    print("PASS: Skill structure and Python syntax are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
