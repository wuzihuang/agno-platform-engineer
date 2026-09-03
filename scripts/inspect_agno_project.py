#!/usr/bin/env python3
"""Inspect an Agno project for version, migration, lifecycle, and production risks."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Iterable


SKIP_DIRS = {
    ".git",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "vendor",
}
PYTHON_COMPONENTS = {
    "Agent",
    "Team",
    "Workflow",
    "AgentOS",
    "Knowledge",
    "SqliteDb",
    "PostgresDb",
    "Skills",
}
WRITE_TOOL_PREFIXES = (
    "add_",
    "apply_",
    "cancel_",
    "create_",
    "delete_",
    "deploy_",
    "execute_",
    "pay_",
    "publish_",
    "refund_",
    "remove_",
    "request_",
    "restart_",
    "send_",
    "set_",
    "submit_",
    "update_",
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    file: str
    line: int
    message: str
    remediation: str


@dataclass
class Facts:
    root: str
    installed_agno_version: str | None = None
    dependency_mentions: list[str] | None = None
    python_files_scanned: int = 0
    component_counts: dict[str, int] | None = None
    has_tests: bool = False
    has_docker_or_k8s: bool = False
    has_agentos: bool = False
    has_tracing: bool = False
    has_evals: bool = False


class Inspector(ast.NodeVisitor):
    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.source = source
        self.findings: list[Finding] = []
        self.component_counts = {name: 0 for name in PYTHON_COMPONENTS}
        self.loop_depth = 0
        self.function_depth = 0
        self.route_depth = 0
        self.tool_functions: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]] = []

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return ""

    @staticmethod
    def _decorator_text(node: ast.expr) -> str:
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _add(
        self,
        severity: str,
        code: str,
        node: ast.AST,
        message: str,
        remediation: str,
    ) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                code=code,
                file=str(self.path),
                line=getattr(node, "lineno", 1),
                message=message,
                remediation=remediation,
            )
        )

    def visit_For(self, node: ast.For) -> None:
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    def visit_While(self, node: ast.While) -> None:
        self.loop_depth += 1
        self.generic_visit(node)
        self.loop_depth -= 1

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        decorators = [self._decorator_text(item) for item in node.decorator_list]
        is_route = any(
            re.search(r"\.(get|post|put|patch|delete|options|websocket)\s*\(", item)
            for item in decorators
        )
        is_tool = any(re.search(r"(^|\.)tool(?:\(|$)", item) for item in decorators)
        if is_tool:
            self.tool_functions.append((node, " ".join(decorators)))

        self.function_depth += 1
        if is_route:
            self.route_depth += 1
        self.generic_visit(node)
        if is_route:
            self.route_depth -= 1
        self.function_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = self._call_name(node)
        if name in PYTHON_COMPONENTS:
            self.component_counts[name] += 1
            if self.loop_depth:
                self._add(
                    "HIGH",
                    "AGNO101",
                    node,
                    f"{name} is constructed inside a loop",
                    "Create reusable Agno components outside user/request loops.",
                )
            if self.route_depth:
                self._add(
                    "HIGH",
                    "AGNO102",
                    node,
                    f"{name} is constructed inside an HTTP/WebSocket route",
                    "Create the component at module scope or in application lifespan and reuse it.",
                )
            if name in {"Agent", "Team", "Workflow", "AgentOS"} and self.function_depth == 0:
                keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
                if "id" not in keywords:
                    self._add(
                        "LOW",
                        "AGNO103",
                        node,
                        f"Module-level {name} has no explicit stable id",
                        "Set id= to stabilize API paths, sessions, scopes, and traces.",
                    )
        self.generic_visit(node)

    def finalize(self) -> None:
        for node, decorators in self.tool_functions:
            if node.name.startswith(WRITE_TOOL_PREFIXES) and "requires_confirmation=True" not in decorators.replace(" ", ""):
                self._add(
                    "MEDIUM",
                    "AGNO201",
                    node,
                    f"Potential write tool {node.name!r} is not visibly confirmation-gated",
                    "Review impact; use @tool(requires_confirmation=True) plus server-side auth/idempotency when appropriate.",
                )


def iter_project_files(root: Path, max_files: int) -> Iterable[Path]:
    count = 0
    for current, dirs, files in os.walk(root):
        dirs[:] = [directory for directory in dirs if directory not in SKIP_DIRS]
        for filename in sorted(files):
            if count >= max_files:
                return
            path = Path(current) / filename
            count += 1
            yield path


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > 2_000_000:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def installed_agno_version() -> str | None:
    try:
        return version("agno")
    except PackageNotFoundError:
        return None


def dependency_mentions(files: list[Path]) -> list[str]:
    mentions: list[str] = []
    candidates = {
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "Pipfile",
        "poetry.lock",
        "pdm.lock",
        "uv.lock",
    }
    for path in files:
        if path.name not in candidates:
            continue
        text = read_text(path)
        if not text:
            continue
        for line in text.splitlines():
            if re.search(r"\b(agno|phidata)\b", line, re.IGNORECASE):
                compact = " ".join(line.strip().split())
                mentions.append(f"{path.name}: {compact[:240]}")
                if len(mentions) >= 20:
                    return mentions
    return mentions


def regex_findings(root: Path, python_files: list[Path]) -> list[Finding]:
    rules = [
        (
            "HIGH",
            "AGNO001",
            re.compile(r"^\s*(?:from|import)\s+phi(?:\.|\s|$)", re.MULTILINE),
            "Legacy phi/phidata import",
            "Migrate imports to agno.* and review the full v3 migration guide.",
        ),
        (
            "HIGH",
            "AGNO002",
            re.compile(r"\bstorage\s*="),
            "Legacy storage= argument",
            "Use db= with the current Db adapters and migrate persisted data.",
        ),
        (
            "HIGH",
            "AGNO003",
            re.compile(r"\b(?:AgentMemory|TeamMemory)\b"),
            "Removed legacy memory class",
            "Use db= plus update_memory_on_run or enable_agentic_memory and optional MemoryManager.",
        ),
        (
            "MEDIUM",
            "AGNO004",
            re.compile(r"\bknowledge_base\s*="),
            "Legacy knowledge_base= argument",
            "Use knowledge= with the unified Knowledge API.",
        ),
        (
            "MEDIUM",
            "AGNO005",
            re.compile(r"\b(?:Playground|FastAPIApp)\s*\("),
            "Legacy service runtime",
            "Use AgentOS and verify the current REST/SSE interfaces.",
        ),
        (
            "LOW",
            "AGNO006",
            re.compile(r"\bmcp_server\s*="),
            "Deprecated AgentOS mcp_server= alias",
            "Use mcp= in new code.",
        ),
        (
            "MEDIUM",
            "AGNO007",
            re.compile(r"\badd_history_to_messages\s*="),
            "Legacy history argument",
            "Use add_history_to_context= and num_history_runs=.",
        ),
        (
            "MEDIUM",
            "AGNO008",
            re.compile(r"\benable_user_memories\s*="),
            "Legacy memory flag",
            "For v3 use update_memory_on_run= or explicitly selected Agentic Memory.",
        ),
        (
            "MEDIUM",
            "AGNO009",
            re.compile(r"\breasoning\s*=\s*True\b"),
            "Legacy implicit reasoning mode",
            "Configure an explicit reasoning_model for current v3 code.",
        ),
        (
            "HIGH",
            "SEC001",
            re.compile(r"cors_allowed_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]"),
            "Wildcard CORS in AgentOS",
            "Use exact production origins; CORS is not authentication.",
        ),
        (
            "HIGH",
            "SEC002",
            re.compile(r"(?:api_key|secret|token)\s*=\s*['\"](?:sk-|ghp_|agno_pat_|eyJ)[^'\"]+['\"]", re.IGNORECASE),
            "Potential hard-coded credential",
            "Remove it from source, rotate it, and load secrets from a secret manager or environment.",
        ),
    ]

    findings: list[Finding] = []
    for path in python_files:
        text = read_text(path)
        if text is None:
            continue
        for severity, code, pattern, message, remediation in rules:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(
                    Finding(
                        severity=severity,
                        code=code,
                        file=str(path.relative_to(root)),
                        line=line,
                        message=message,
                        remediation=remediation,
                    )
                )
    return findings


def project_level_findings(
    root: Path,
    files: list[Path],
    python_text: str,
    has_agentos: bool,
    has_tracing: bool,
    has_evals: bool,
    has_production_files: bool,
) -> list[Finding]:
    findings: list[Finding] = []

    def add(severity: str, code: str, message: str, remediation: str) -> None:
        findings.append(Finding(severity, code, str(root), 1, message, remediation))

    auto_memory = re.search(r"\bupdate_memory_on_run\s*=\s*True\b", python_text)
    agentic_memory = re.search(r"\benable_agentic_memory\s*=\s*True\b", python_text)
    if auto_memory and agentic_memory:
        add(
            "HIGH",
            "AGNO301",
            "Both automatic and Agentic Memory flags are enabled in the project",
            "Select one memory mode per Agent and add memory precision/cost tests.",
        )
    if (auto_memory or agentic_memory) and not re.search(r"\buser_id\b", python_text):
        add(
            "HIGH",
            "AGNO302",
            "Memory is enabled but no user_id usage was found",
            "Pass a stable trusted user_id on every run or enable AgentOS JWT user isolation.",
        )

    if re.search(r"authorization\s*=\s*True\b", python_text) and not re.search(
        r"user_isolation\s*=\s*True\b", python_text
    ):
        add(
            "HIGH",
            "SEC101",
            "Authorization appears enabled without explicit user_isolation=True",
            "For multi-user production use AuthorizationConfig(user_isolation=True) and test ownership.",
        )

    if has_agentos and has_production_files and not re.search(r"authorization\s*=", python_text):
        add(
            "MEDIUM",
            "SEC102",
            "Production-shaped AgentOS project has no visible authorization configuration",
            "Enable JWT/RBAC in production and fail startup when it is disabled.",
        )

    if has_production_files and "SqliteDb" in python_text and "PostgresDb" not in python_text:
        add(
            "MEDIUM",
            "OPS101",
            "Production-shaped project appears to use only SQLite",
            "Use PostgreSQL for multi-replica or multi-user production deployments.",
        )

    if has_agentos and not has_tracing:
        add(
            "LOW",
            "OBS101",
            "AgentOS found without visible tracing configuration",
            "Enable tracing and verify prompt/tool payload redaction and retention.",
        )
    if has_agentos and not has_evals:
        add(
            "LOW",
            "EVAL101",
            "No Agno eval imports or eval directory were found",
            "Add repeatable accuracy/reliability/performance and security regression cases.",
        )

    has_tests = any("tests" in path.parts or path.name.startswith("test_") for path in files)
    if has_agentos and not has_tests:
        add(
            "LOW",
            "TEST101",
            "No tests directory/test files were found",
            "Add unit, AgentOS API contract, user-isolation, and concurrency tests.",
        )

    return findings


def severity_rank(value: str) -> int:
    return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(value, 9)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="Project root")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on medium findings too")
    parser.add_argument("--max-files", type=int, default=5000)
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    files = list(iter_project_files(root, max_files=max(args.max_files, 1)))
    python_files = [path for path in files if path.suffix == ".py"]
    has_production_files = any(
        path.name in {"Dockerfile", "docker-compose.yml", "compose.yml"}
        or "k8s" in path.parts
        or "helm" in path.parts
        or path.name.endswith(("deployment.yaml", "deployment.yml"))
        for path in files
    )

    facts = Facts(
        root=str(root),
        installed_agno_version=installed_agno_version(),
        dependency_mentions=dependency_mentions(files),
        python_files_scanned=len(python_files),
        component_counts={name: 0 for name in sorted(PYTHON_COMPONENTS)},
        has_tests=any("tests" in path.parts or path.name.startswith("test_") for path in files),
        has_docker_or_k8s=has_production_files,
    )

    findings = regex_findings(root, python_files)
    all_python_text: list[str] = []
    for path in python_files:
        text = read_text(path)
        if text is None:
            continue
        all_python_text.append(text)
        relative = path.relative_to(root)
        try:
            tree = ast.parse(text, filename=str(relative))
        except SyntaxError as exc:
            findings.append(
                Finding(
                    "HIGH",
                    "PY001",
                    str(relative),
                    exc.lineno or 1,
                    f"Python syntax error: {exc.msg}",
                    "Fix syntax before evaluating Agno behavior.",
                )
            )
            continue
        inspector = Inspector(relative, text)
        inspector.visit(tree)
        inspector.finalize()
        findings.extend(inspector.findings)
        assert facts.component_counts is not None
        for name, count in inspector.component_counts.items():
            facts.component_counts[name] += count

    python_blob = "\n".join(all_python_text)
    facts.has_agentos = bool(facts.component_counts and facts.component_counts.get("AgentOS"))
    facts.has_tracing = bool(
        re.search(r"\btracing\s*=|setup_tracing\s*\(", python_blob)
    )
    facts.has_evals = bool(
        re.search(r"agno\.eval|AccuracyEval|ReliabilityEval|PerformanceEval", python_blob)
        or any("eval" in part.lower() for path in files for part in path.parts)
    )
    findings.extend(
        project_level_findings(
            root,
            files,
            python_blob,
            facts.has_agentos,
            facts.has_tracing,
            facts.has_evals,
            has_production_files,
        )
    )

    unique = {
        (item.severity, item.code, item.file, item.line, item.message): item for item in findings
    }
    findings = sorted(
        unique.values(),
        key=lambda item: (severity_rank(item.severity), item.file, item.line, item.code),
    )

    counts = {severity: sum(item.severity == severity for item in findings) for severity in ("HIGH", "MEDIUM", "LOW")}

    if args.as_json:
        print(
            json.dumps(
                {
                    "facts": asdict(facts),
                    "summary": counts,
                    "findings": [asdict(item) for item in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print("Agno project inspection")
        print(f"Root: {root}")
        print(f"Installed Agno: {facts.installed_agno_version or 'not installed in this interpreter'}")
        print(f"Python files scanned: {facts.python_files_scanned}")
        print(f"Components: {facts.component_counts}")
        if facts.dependency_mentions:
            print("Dependency mentions:")
            for mention in facts.dependency_mentions:
                print(f"  - {mention}")
        print(f"Findings: HIGH={counts['HIGH']} MEDIUM={counts['MEDIUM']} LOW={counts['LOW']}")
        for item in findings:
            print(f"\n[{item.severity}] {item.code} {item.file}:{item.line}")
            print(f"  {item.message}")
            print(f"  Fix: {item.remediation}")
        if not findings:
            print("No known pattern-level risks found. This is not a substitute for runtime tests or evals.")

    if counts["HIGH"]:
        return 1
    if args.strict and counts["MEDIUM"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
