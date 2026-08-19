"""Architectural boundary contract tests for fbf-core."""

import ast
import os

import fbf.core


def test_core_has_zero_cli_imports() -> None:
    """Asserts that fbf-core production code NEVER imports from CLI."""
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
    for root, _, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                with open(p, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=p)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            assert not alias.name.startswith("cli") and not alias.name.startswith(
                                "fbf.cli"
                            ), f"Forbidden CLI import in {p}:{node.lineno}: {alias.name}"
                    elif isinstance(node, ast.ImportFrom):
                        mod = node.module or ""
                        assert not mod.startswith("cli") and not mod.startswith("fbf.cli"), (
                            f"Forbidden CLI import in {p}:{node.lineno}: {mod}"
                        )


def test_domain_downward_layering() -> None:
    """Asserts that domain layer does not import execution, study, optimization, or persistence."""
    domain_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../src/fbf/core/domain")
    )
    forbidden_prefixes = (
        "fbf.core.execution",
        "fbf.core.study",
        "fbf.core.optimization",
        "fbf.core.persistence",
        "cli",
        "fbf.cli",
    )
    for root, _, files in os.walk(domain_dir):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                with open(p, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=p)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            has_forbidden = any(
                                alias.name.startswith(pre) for pre in forbidden_prefixes
                            )
                            assert not has_forbidden, (
                                f"Domain layer upward import in {p}:{node.lineno}: {alias.name}"
                            )
                    elif isinstance(node, ast.ImportFrom):
                        mod = node.module or ""
                        assert not any(mod.startswith(pre) for pre in forbidden_prefixes), (
                            f"Domain layer upward import in {p}:{node.lineno}: {mod}"
                        )


def test_execution_optimization_isolation() -> None:
    """Asserts that execution layer never imports optimization."""
    exec_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../src/fbf/core/execution")
    )
    for root, _, files in os.walk(exec_dir):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                with open(p, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=p)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            assert not alias.name.startswith("fbf.core.optimization"), (
                                f"Execution imports optimization in {p}:{node.lineno}: {alias.name}"
                            )
                    elif isinstance(node, ast.ImportFrom):
                        mod = node.module or ""
                        assert not mod.startswith("fbf.core.optimization"), (
                            f"Execution imports optimization in {p}:{node.lineno}: {mod}"
                        )


def test_public_facade_symbols() -> None:
    """Validates public facade symbols exposed by fbf.core."""
    expected_symbols = {
        "StudyConfiguration",
        "StudyPlanResult",
        "build_study_plan",
        "ExecutionMode",
        "ExecutionOptions",
        "execute_study_plan",
        "ResearchExecutionResult",
        "optimize_study_swr",
        "StudyRepository",
        "create_study_repository",
        "CoreError",
        "__version__",
    }
    actual_symbols = set(fbf.core.__all__)
    assert expected_symbols.issubset(
        actual_symbols
    ), f"Missing facade symbols: {expected_symbols - actual_symbols}"
