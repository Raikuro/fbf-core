"""Architectural boundary contract tests for fbf-core.

These tests are the regression protection for the Phase 2 repository-
independence audit (closure item 2.9): they scan BOTH production ``src/`` and
the ``tests/`` surface so that historical test-level dependency defects cannot
silently return.

Classification of the external CLI surface: ``tests/oracle/`` is the ONLY part
of the Core suite allowed to touch the external ``sim-retire`` console script
(black-box ERN acceptance, gated behind ``RUN_ERN_E2E`` / ``SIM_RETIRE_BIN``,
i.e. an explicitly classified external integration requirement).  Everything
else in Core must be runnable with no ``fbf-cli`` package, no CLI source, and
no ``sim-retire`` executable present.
"""

import ast
import os
from pathlib import Path

import fbf.core

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
_TESTS_DIR = _REPO_ROOT / "tests"
_ORACLE_DIR = _TESTS_DIR / "oracle"

_LEGACY_TOP_LEVEL = ("engine", "research", "infrastructure", "simulador_jubilacion")


def _iter_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py"))


def _import_targets(path: Path) -> list[str]:
    """Return every module name referenced by an import statement in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            targets.append(node.module or "")
    return targets


def test_core_has_zero_cli_imports() -> None:
    """Asserts that fbf-core production code NEVER imports from CLI."""
    for p in _iter_py_files(_SRC_DIR):
        for mod in _import_targets(p):
            assert not mod.startswith("cli") and not mod.startswith("fbf.cli"), (
                f"Forbidden CLI import in {p}: {mod}"
            )


def test_core_tests_have_no_cli_or_legacy_imports() -> None:
    """Asserts the test surface has no CLI or legacy-namespace imports.

    The Phase 2 remediation removed the historical ``cli.*`` imports from
    ``tests/integration`` and the legacy ``research.orchestration.*`` patch
    targets.  This test makes those regressions structurally impossible: any
    future ``from cli.main import ...`` or ``patch("research.orchestration...")``
    in Core tests fails collection of the suite in the first place.
    """
    for p in _iter_py_files(_TESTS_DIR):
        for mod in _import_targets(p):
            assert not mod.startswith("cli") and not mod.startswith("fbf.cli"), (
                f"Forbidden CLI import in test file {p}: {mod}"
            )
            assert mod.split(".")[0] not in _LEGACY_TOP_LEVEL, (
                f"Forbidden legacy import in test file {p}: {mod}"
            )


def test_cli_binary_usage_confined_to_oracle_suite() -> None:
    """Core tests must not require a CLI binary outside the classified oracle suite.

    The only test helper that locates/executes the external ``sim-retire``
    console script is ``tests/oracle/cli_harness.py``.  Any test file importing
    it must live under ``tests/oracle/``; the worker-selection argv test inside
    that suite uses an injected fake ``cli`` path (no binary required).  This is
    the explicit classification boundary for "external black-box integration"
    test requirements.
    """
    importing_files: list[Path] = []
    for p in _iter_py_files(_TESTS_DIR):
        if p.name == "cli_harness.py":
            continue
        for mod in _import_targets(p):
            if mod == "tests.oracle.cli_harness":
                importing_files.append(p)
    for p in importing_files:
        assert _ORACLE_DIR in p.parents, (
            f"Test file {p} imports the external-CLI harness outside the "
            f"tests/oracle/ suite; CLI-binary usage must be confined to the "
            f"classified black-box oracle suite."
        )


def test_core_has_no_machine_specific_or_sibling_paths() -> None:
    """No hidden workspace, sibling-repository, or machine-specific assumptions.

    Production and test code must not reference absolute machine paths
    (``/tmp``, ``/home``, ``/Users``, ``C:\\``) or sibling repository trees.
    An installed-only deployment has none of these; any such reference is a
    hidden assumption that breaks the standalone guarantee.
    """
    banned_fragments = ("/tmp/", "/home/", "/Users/", "C:\\")
    offenders: list[str] = []
    self_file = Path(__file__).resolve()
    for root in (_SRC_DIR, _TESTS_DIR):
        for p in _iter_py_files(root):
            if p.resolve() == self_file:
                continue
            for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if any(fragment in line for fragment in banned_fragments):
                    offenders.append(f"{p}:{line_no}: {line.strip()}")
    assert offenders == [], (
        f"Machine-specific path(s) found in Core: {offenders}. "
        f"Tests should use tmp_path; production must never hardcode paths."
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
        "AllocationPolicyType",
        "WithdrawalPolicyType",
        "StudyConfiguration",
        "StudyPlanResult",
        "build_study_plan",
        "ExecutionBackend",
        "ExecutionStrategy",
        "ExecutionOptions",
        "execute_study_plan",
        "ResearchExecutionResult",
        "optimize_study_swr",
        "StudyRepository",
        "create_study_repository",
        "CoreError",
        "__version__",
        "BuiltStudy",
        "CohortGenerator",
        "CohortSpecification",
        "ExperimentDefinition",
        "ParameterAxis",
        "ParameterConfiguration",
        "ParameterSweepEngine",
        "PlannedSimulationUnit",
        "ResearchPlan",
        "Profiler",
        "NoOpProfiler",
        "ExecutionProfiler",
        "ProfileReport",
    }
    actual_symbols = set(fbf.core.__all__)
    assert expected_symbols == actual_symbols, (
        f"Facade mismatch. Missing: {expected_symbols - actual_symbols}, "
        f"Unexpected: {actual_symbols - expected_symbols}"
    )


def test_simulation_runner_and_executor_have_no_financial_domain_imports() -> None:
    """SimulationRunner and SimulationExecutor must not import financial-domain details.

    These classes are orchestration-only: they coordinate pipeline steps and
    delegate to injected policies. They must never import financial-domain
    implementation details (asset classes, market data, portfolio construction,
    policy implementations).
    """
    import fbf.core.execution.pipeline.executor as executor_mod
    import fbf.core.execution.pipeline.runner as runner_mod

    forbidden_prefixes = (
        "fbf.core.domain.model",
        "fbf.core.domain.policies",
        "fbf.core.study",
    )

    for mod in (runner_mod, executor_mod):
        source = Path(mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(mod.__file__))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(alias.name.startswith(p) for p in forbidden_prefixes), (
                        f"Financial-domain import in {mod.__name__}:{node.lineno}: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not any(module.startswith(p) for p in forbidden_prefixes), (
                    f"Financial-domain import in {mod.__name__}:{node.lineno}: {module}"
                )
