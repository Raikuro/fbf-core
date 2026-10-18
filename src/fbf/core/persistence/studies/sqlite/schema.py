"""SQLite schema DDL constants (v0.5).

Schema version 4 adds incremental execution state to ``execution_results``:
``status``, ``attempt_id``, ``completed_units``, ``updated_at``,
``completed_at``, and ``error``.  Incomplete executions are invisible to the
completed-result loading API.  Schema version 2 added the ``deleted_at``
soft-delete columns to ``experiments`` and ``research_plans``.
"""

SCHEMA_VERSION: int = 4

PRAGMA_FOREIGN_KEYS = "PRAGMA foreign_keys = ON"
PRAGMA_WAL = "PRAGMA journal_mode = WAL"
PRAGMA_SYNCHRONOUS = "PRAGMA synchronous = NORMAL"

CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL
);
"""

CREATE_EXPERIMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    revision TEXT NOT NULL,
    description TEXT NOT NULL,
    dataset_identifier TEXT,
    horizon_months INTEGER NOT NULL CHECK(horizon_months > 0),
    initial_wealth TEXT NOT NULL,
    initial_wealth_currency TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    UNIQUE(name, revision)
);
"""

CREATE_COHORTS_TABLE = """
CREATE TABLE IF NOT EXISTS cohorts (
    cohort_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    start_date TEXT NOT NULL,
    cohort_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(experiment_id, start_date)
);
"""

CREATE_PARAMETER_CONFIGURATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS parameter_configurations (
    param_config_id TEXT PRIMARY KEY,
    params_json TEXT NOT NULL,
    params_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
"""

CREATE_POLICIES_TABLE = """
CREATE TABLE IF NOT EXISTS policies (
    policy_id TEXT PRIMARY KEY,
    policy_type TEXT NOT NULL,
    params_json TEXT NOT NULL,
    params_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(policy_type, params_hash)
);
"""

CREATE_EXPERIMENT_POLICIES_TABLE = """
CREATE TABLE IF NOT EXISTS experiment_policies (
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    policy_id TEXT NOT NULL REFERENCES policies(policy_id),
    policy_kind TEXT NOT NULL CHECK(policy_kind IN ("allocation", "withdrawal")),
    policy_index INTEGER NOT NULL CHECK(policy_index >= 0),
    PRIMARY KEY(experiment_id, policy_kind, policy_index),
    UNIQUE(experiment_id, policy_id, policy_kind)
);
"""

CREATE_RESEARCH_PLANS_TABLE = """
CREATE TABLE IF NOT EXISTS research_plans (
    plan_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(experiment_id),
    created_at TEXT NOT NULL,
    unit_count INTEGER NOT NULL CHECK(unit_count > 0),
    status TEXT NOT NULL CHECK(status IN ("planned","executing","completed","failed")),
    deleted_at TEXT
);
"""

CREATE_PLANNED_UNITS_TABLE = """
CREATE TABLE IF NOT EXISTS planned_units (
    unit_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES research_plans(plan_id),
    unit_index INTEGER NOT NULL CHECK(unit_index >= 0),
    cohort_id TEXT NOT NULL REFERENCES cohorts(cohort_id),
    param_config_id TEXT NOT NULL REFERENCES parameter_configurations(param_config_id),
    allocation_policy_id TEXT NOT NULL REFERENCES policies(policy_id),
    withdrawal_policy_id TEXT NOT NULL REFERENCES policies(policy_id),
    initial_portfolio_json TEXT NOT NULL,
    final_value_target TEXT,
    UNIQUE(plan_id, unit_index),
    UNIQUE(plan_id, cohort_id, param_config_id)
);
"""

CREATE_EXECUTION_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS execution_results (
    result_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL UNIQUE REFERENCES research_plans(plan_id),
    attempt_id TEXT,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK(status IN ('executing', 'completed', 'failed')),
    executed_at TEXT NOT NULL,
    updated_at TEXT,
    completed_at TEXT,
    duration_seconds REAL NOT NULL CHECK(duration_seconds >= 0),
    success_count INTEGER NOT NULL CHECK(success_count >= 0),
    failure_count INTEGER NOT NULL CHECK(failure_count >= 0),
    completed_units INTEGER NOT NULL DEFAULT 0 CHECK(completed_units >= 0),
    total_units INTEGER NOT NULL CHECK(total_units > 0),
    error TEXT
);
"""

CREATE_SIMULATION_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS simulation_results (
    execution_result_id TEXT NOT NULL REFERENCES execution_results(result_id),
    unit_index INTEGER NOT NULL,
    month_index INTEGER NOT NULL,
    monthly_payload_json TEXT NOT NULL,
    statistics_payload_json TEXT,
    final_month INTEGER NOT NULL CHECK(final_month IN (0,1)),
    PRIMARY KEY(execution_result_id, unit_index, month_index)
);
"""



CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_cohorts ON cohorts(experiment_id, start_date);",
    "CREATE INDEX IF NOT EXISTS idx_policies_type ON policies(policy_type);",
    "CREATE INDEX IF NOT EXISTS idx_plans_experiment ON research_plans(experiment_id);",
    "CREATE INDEX IF NOT EXISTS idx_units_plan ON planned_units(plan_id, unit_index);",
    "CREATE INDEX IF NOT EXISTS idx_results_plan ON execution_results(plan_id);",
    "CREATE INDEX IF NOT EXISTS idx_results_status ON execution_results(status);",
    "CREATE INDEX IF NOT EXISTS idx_results_execution ON "
    "simulation_results(execution_result_id, unit_index, month_index);",
    "CREATE INDEX IF NOT EXISTS idx_experiments_deleted ON experiments(deleted_at);",
    "CREATE INDEX IF NOT EXISTS idx_plans_deleted ON research_plans(deleted_at);",
]

# Migrations applied after CREATE TABLE DDL for databases created by an older
# schema version (CREATE TABLE IF NOT EXISTS cannot add columns).
MIGRATIONS = [
    (
        "experiments",
        "deleted_at",
        "ALTER TABLE experiments ADD COLUMN deleted_at TEXT",
    ),
    (
        "research_plans",
        "deleted_at",
        "ALTER TABLE research_plans ADD COLUMN deleted_at TEXT",
    ),
    (
        "planned_units",
        "final_value_target",
        "ALTER TABLE planned_units ADD COLUMN final_value_target TEXT",
    ),
    (
        "execution_results",
        "attempt_id",
        "ALTER TABLE execution_results ADD COLUMN attempt_id TEXT",
    ),
    (
        "execution_results",
        "status",
        "ALTER TABLE execution_results ADD COLUMN status TEXT NOT NULL "
        "DEFAULT 'completed'",
    ),
    (
        "execution_results",
        "updated_at",
        "ALTER TABLE execution_results ADD COLUMN updated_at TEXT",
    ),
    (
        "execution_results",
        "completed_at",
        "ALTER TABLE execution_results ADD COLUMN completed_at TEXT",
    ),
    (
        "execution_results",
        "completed_units",
        "ALTER TABLE execution_results ADD COLUMN completed_units INTEGER "
        "NOT NULL DEFAULT 0",
    ),
    (
        "execution_results",
        "error",
        "ALTER TABLE execution_results ADD COLUMN error TEXT",
    ),
]

# Data backfill applied after column migrations.  These statements are
# idempotent and only ever promote legacy completed rows to the v4 shape; rows
# written by the streaming API are left untouched.
DATA_MIGRATIONS = [
    "UPDATE execution_results SET attempt_id = result_id WHERE attempt_id IS NULL",
    "UPDATE execution_results SET completed_units = total_units "
    "WHERE status = 'completed' AND completed_units = 0",
    "UPDATE execution_results SET completed_at = executed_at "
    "WHERE status = 'completed' AND completed_at IS NULL",
    "UPDATE execution_results SET updated_at = "
    "COALESCE(completed_at, executed_at) WHERE updated_at IS NULL",
]

ALL_DDL = [
    CREATE_SCHEMA_VERSION_TABLE,
    CREATE_EXPERIMENTS_TABLE,
    CREATE_COHORTS_TABLE,
    CREATE_PARAMETER_CONFIGURATIONS_TABLE,
    CREATE_POLICIES_TABLE,
    CREATE_EXPERIMENT_POLICIES_TABLE,
    CREATE_RESEARCH_PLANS_TABLE,
    CREATE_PLANNED_UNITS_TABLE,
    CREATE_EXECUTION_RESULTS_TABLE,
    CREATE_SIMULATION_RESULTS_TABLE,
]

# Index DDL is applied separately, AFTER migrations, because indexes added by a
# newer schema version may reference columns that do not exist yet on databases
# created by an older version (e.g. idx_experiments_deleted on ``deleted_at``).
INDEX_DDL = [*CREATE_INDEXES]
