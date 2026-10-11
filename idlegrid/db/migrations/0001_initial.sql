CREATE TABLE IF NOT EXISTS schema_migrations (
  version     VARCHAR(64) PRIMARY KEY,
  applied_at  DATETIME(3) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE users (
  user_id       VARCHAR(16)  PRIMARY KEY,
  display_name  VARCHAR(64)  NOT NULL UNIQUE,
  token_sha256  CHAR(64)     NOT NULL UNIQUE,
  is_admin      BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at    DATETIME(3)  NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE nodes (
  node_id             VARCHAR(64)  PRIMARY KEY,
  owner_user_id       VARCHAR(16)  NOT NULL,
  hostname            VARCHAR(255) NOT NULL,
  os                  VARCHAR(16)  NOT NULL,
  os_release          VARCHAR(64),
  arch                VARCHAR(16),
  python_version      VARCHAR(16),
  agent_version       VARCHAR(16),
  cpu_count           INT,
  ram_total_mb        INT,
  perf_score          FLOAT,
  input_method        VARCHAR(32),
  input_precision     VARCHAR(8),
  can_prevent_sleep   BOOLEAN,
  worker_env_hash     VARCHAR(64),
  accepting_jobs      BOOLEAN      NOT NULL DEFAULT TRUE,
  require_ac_power    BOOLEAN      NOT NULL DEFAULT TRUE,
  dedicated_mode      BOOLEAN      NOT NULL DEFAULT FALSE,
  status              VARCHAR(16)  NOT NULL,
  host_state          VARCHAR(8),
  cpu_percent         FLOAT,
  host_cpu_percent    FLOAT,
  ram_percent         FLOAT,
  ram_available_mb    INT,
  user_inactivity_sec FLOAT NULL,
  on_ac_power         BOOLEAN NULL,
  battery_percent     FLOAT NULL,
  current_attempt_id  VARCHAR(40) NULL,
  available_since     DATETIME(3) NULL,
  predicted_q10_sec   FLOAT NULL,
  predicted_q20_sec   FLOAT NULL,
  predicted_q50_sec   FLOAT NULL,
  prediction_method   VARCHAR(20) NULL,
  prediction_model    VARCHAR(64) NULL,
  prediction_at       DATETIME(3) NULL,
  last_ip             VARCHAR(45),
  last_heartbeat_at   DATETIME(3) NOT NULL,
  first_seen_at       DATETIME(3) NOT NULL,
  CONSTRAINT fk_nodes_owner FOREIGN KEY (owner_user_id) REFERENCES users(user_id),
  INDEX ix_nodes_status (status),
  INDEX ix_nodes_last_hb (last_heartbeat_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE node_status_events (
  event_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
  node_id      VARCHAR(64) NOT NULL,
  from_status  VARCHAR(16) NULL,
  to_status    VARCHAR(16) NOT NULL,
  at           DATETIME(3) NOT NULL,
  INDEX ix_nse_node_at (node_id, at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- No FK on node_id: rows logged before a node's first heartbeat (Phase 0 CSVs) must still be insertable.
CREATE TABLE usage_samples (
  node_id             VARCHAR(64) NOT NULL,
  ts_utc              DATETIME(3) NOT NULL,
  tz_offset_min       SMALLINT    NOT NULL,
  cpu_percent         FLOAT       NOT NULL,
  host_cpu_percent    FLOAT       NOT NULL,
  ram_percent         FLOAT       NOT NULL,
  user_inactivity_sec FLOAT       NULL,
  input_method        VARCHAR(32) NOT NULL,
  input_precision     VARCHAR(8)  NOT NULL,
  host_state          VARCHAR(8)  NOT NULL,
  on_ac_power         BOOLEAN     NULL,
  battery_percent     FLOAT       NULL,
  job_running         BOOLEAN     NOT NULL DEFAULT FALSE,
  agent_version       VARCHAR(16) NOT NULL,
  received_at         DATETIME(3) NOT NULL,
  PRIMARY KEY (node_id, ts_utc),
  INDEX ix_usage_ts (ts_utc)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE experiment_runs (
  run_id       VARCHAR(16) PRIMARY KEY,
  name         VARCHAR(128) NOT NULL,
  policy       VARCHAR(32)  NOT NULL,
  notes        TEXT,
  config       JSON,
  is_active    BOOLEAN      NOT NULL DEFAULT FALSE,
  started_at   DATETIME(3)  NOT NULL,
  finished_at  DATETIME(3)  NULL,
  summary      JSON         NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE hpo_studies (
  study_id                VARCHAR(16)  PRIMARY KEY,
  optuna_study_name       VARCHAR(128) NOT NULL UNIQUE,
  user_id                 VARCHAR(16)  NOT NULL,
  name                    VARCHAR(128) NOT NULL,
  direction               VARCHAR(8)   NOT NULL,
  spec                    JSON         NOT NULL,
  status                  VARCHAR(12)  NOT NULL,
  n_trials                INT          NOT NULL,
  max_parallel            INT          NOT NULL,
  asked                   INT          NOT NULL DEFAULT 0,
  completed               INT          NOT NULL DEFAULT 0,
  failed                  INT          NOT NULL DEFAULT 0,
  best_value              DOUBLE       NULL,
  best_params             JSON         NULL,
  best_trial_number       INT          NULL,
  objective_bundle_path   VARCHAR(255) NOT NULL,
  objective_bundle_sha256 CHAR(64)     NOT NULL,
  priority                INT          NOT NULL DEFAULT 0,
  experiment_run_id       VARCHAR(16)  NULL,
  created_at              DATETIME(3)  NOT NULL,
  finished_at             DATETIME(3)  NULL,
  CONSTRAINT fk_studies_user FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_studies_run  FOREIGN KEY (experiment_run_id) REFERENCES experiment_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE jobs (
  job_id                VARCHAR(16)  PRIMARY KEY,
  user_id               VARCHAR(16)  NOT NULL,
  job_name              VARCHAR(128) NOT NULL,
  kind                  VARCHAR(12)  NOT NULL,
  status                VARCHAR(12)  NOT NULL,
  priority              INT          NOT NULL DEFAULT 0,
  entrypoint            VARCHAR(255) NOT NULL,
  args                  JSON,
  manifest              JSON         NOT NULL,
  bundle_path           VARCHAR(255) NOT NULL,
  bundle_sha256         CHAR(64)     NOT NULL,
  bundle_size           BIGINT       NOT NULL,
  estimated_runtime_sec INT          NOT NULL,
  timeout_seconds       INT          NOT NULL,
  ram_required_mb       INT          NOT NULL,
  study_id              VARCHAR(16)  NULL,
  trial_number          INT          NULL,
  experiment_run_id     VARCHAR(16)  NULL,
  current_attempt_id    VARCHAR(40)  NULL,
  final_attempt_id      VARCHAR(40)  NULL,
  attempts_count        INT          NOT NULL DEFAULT 0,
  created_at            DATETIME(3)  NOT NULL,
  queued_at             DATETIME(3)  NOT NULL,
  started_at            DATETIME(3)  NULL,
  completed_at          DATETIME(3)  NULL,
  exit_code             INT          NULL,
  error_message         TEXT         NULL,
  objective_value       DOUBLE       NULL,
  CONSTRAINT fk_jobs_user  FOREIGN KEY (user_id) REFERENCES users(user_id),
  CONSTRAINT fk_jobs_study FOREIGN KEY (study_id) REFERENCES hpo_studies(study_id),
  CONSTRAINT fk_jobs_run   FOREIGN KEY (experiment_run_id) REFERENCES experiment_runs(run_id),
  UNIQUE KEY uq_jobs_trial (study_id, trial_number),
  INDEX ix_jobs_queue (status, priority, queued_at),
  INDEX ix_jobs_user (user_id, created_at),
  INDEX ix_jobs_run (experiment_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE job_attempts (
  attempt_id         VARCHAR(40)  PRIMARY KEY,
  job_id             VARCHAR(16)  NOT NULL,
  attempt_no         INT          NOT NULL,
  node_id            VARCHAR(64)  NOT NULL,
  status             VARCHAR(12)  NOT NULL,
  policy_name        VARCHAR(32)  NOT NULL,
  experiment_run_id  VARCHAR(16)  NULL,
  assigned_at        DATETIME(3)  NOT NULL,
  started_at         DATETIME(3)  NULL,
  ended_at           DATETIME(3)  NULL,
  end_reason         VARCHAR(32)  NULL,
  paused_since       DATETIME(3)  NULL,
  active_seconds     DOUBLE       NOT NULL DEFAULT 0,
  pause_count        INT          NOT NULL DEFAULT 0,
  total_pause_sec    DOUBLE       NOT NULL DEFAULT 0,
  predicted_q20_sec  FLOAT        NULL,
  predicted_q50_sec  FLOAT        NULL,
  required_sec       FLOAT        NULL,
  exit_code          INT          NULL,
  peak_cpu_percent   FLOAT        NULL,
  peak_ram_mb        FLOAT        NULL,
  log_bytes          BIGINT       NOT NULL DEFAULT 0,
  result_path        VARCHAR(255) NULL,
  result_sha256      CHAR(64)     NULL,
  metrics            JSON         NULL,
  CONSTRAINT fk_att_job  FOREIGN KEY (job_id)  REFERENCES jobs(job_id),
  CONSTRAINT fk_att_node FOREIGN KEY (node_id) REFERENCES nodes(node_id),
  UNIQUE KEY uq_att_job_no (job_id, attempt_no),
  INDEX ix_att_node_status (node_id, status),
  INDEX ix_att_status_paused (status, paused_since),
  INDEX ix_att_run (experiment_run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE node_commands (
  command_id      VARCHAR(16)  PRIMARY KEY,
  node_id         VARCHAR(64)  NOT NULL,
  attempt_id      VARCHAR(40)  NULL,
  type            VARCHAR(8)   NOT NULL,
  payload         JSON         NOT NULL,
  created_at      DATETIME(3)  NOT NULL,
  delivered_at    DATETIME(3)  NULL,
  delivery_count  INT          NOT NULL DEFAULT 0,
  acked_at        DATETIME(3)  NULL,
  ok              BOOLEAN      NULL,
  error           VARCHAR(255) NULL,
  CONSTRAINT fk_cmd_node FOREIGN KEY (node_id) REFERENCES nodes(node_id),
  INDEX ix_cmd_pending (node_id, acked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE oracle_models (
  model_id     VARCHAR(64)  PRIMARY KEY,
  path         VARCHAR(255) NOT NULL,
  variant      VARCHAR(16)  NOT NULL,
  trained_at   DATETIME(3)  NOT NULL,
  train_from   DATETIME(3)  NOT NULL,
  train_to     DATETIME(3)  NOT NULL,
  metrics      JSON         NOT NULL,
  is_active    BOOLEAN      NOT NULL DEFAULT FALSE,
  notes        TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
