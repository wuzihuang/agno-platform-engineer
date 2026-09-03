#!/usr/bin/env python3
"""Copy the production AgentOS template into a new project directory."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


def normalize_project_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not normalized:
        raise ValueError("Project name must contain at least one letter or number")
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="New project directory")
    parser.add_argument("--project-name", help="Python package metadata project name")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Copy into a non-empty directory without deleting unrelated files",
    )
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    template = skill_root / "templates" / "production_agentos"
    if not template.is_dir():
        print(f"Template directory is missing: {template}", file=sys.stderr)
        return 2

    target = Path(args.target).expanduser().resolve()
    if target.exists() and any(target.iterdir()) and not args.force:
        print(
            f"Target is not empty: {target}\nUse --force only after reviewing existing files.",
            file=sys.stderr,
        )
        return 2

    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, target, dirs_exist_ok=True)

    project_name = normalize_project_name(args.project_name or target.name)
    pyproject = target / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = text.replace('name = "agno-production-template"', f'name = "{project_name}"')
    pyproject.write_text(text, encoding="utf-8")

    print(f"Created Agno AgentOS project: {target}")
    print("Next steps:")
    print(f"  cd {target}")
    print("  cp .env.example .env")
    print("  uv sync --extra dev")
    print("  docker compose up -d postgres")
    print("  set -a; . ./.env; set +a")
    print("  uv run pytest")
    print("  uv run agno-app")
    print("Before production, enable JWT, keep user_isolation=True, replace demo tools, and run security/load/eval gates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
