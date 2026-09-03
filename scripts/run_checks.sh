#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

python "$ROOT/scripts/validate_skill.py" "$ROOT"
python -m compileall -q "$ROOT/scripts" "$ROOT/templates"

echo "PASS: Skill and template checks completed"
