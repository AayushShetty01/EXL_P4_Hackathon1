# PROJECT CONTEXT: ModelPassport (version 1.0)

This document is the single source of truth for the project. It is kept in `docs/PROJECT_CONTEXT.md`. If an idea conflicts with this document, this document wins. If something here looks wrong, raise it in the team chat so it can be changed for everyone at once.

## 1. The hackathon and the challenge

Event: EXL x UCD Data and AI Hackathon 2026. Our team chose Challenge 04, "Agentic model risk factory".

Client scenario: a Tier 1 UK retail bank runs about 250 credit, fraud and pricing models built in SAS, R and Python. Under PRA SS1/23 (the UK regulator's model risk management principles for banks) each model needs current documentation and independent validation. Today the documents are outdated and each validation takes 8 to 12 weeks.

What the brief asks us to build:

1. Document 3 to 5 sample models and build their inventory records.
2. Use AI agents to rebuild one SAS or R model in Python, with parity proof.
3. Auto generate a validation report on performance, stability and fairness.

Suggested approach in the brief, with humans reviewing at each gate: Discover, Document, Redevelop, Validate, Monitor.

Constraints from the brief: public or synthetic data only, never personal data. Azure ML and MLflow are preferred but any stack is allowed.

Judging weights: Business impact 30%, Technical approach 25%, Innovation 20%, Responsible AI 15%, Presentation and Q&A 10%.

Submission pack: solution deck (max 10 slides), demo video (max 3 minutes), public code repository with README and setup steps, one page architecture diagram, one page Responsible AI note.

## 2. Our solution in short

ModelPassport is an agentic factory. It takes a legacy model folder (code, stale documents, data) and produces a Model Passport: one evidence pack per model with five stamps. Each stamp is produced by an AI agent or by a deterministic engine, and a human reviewer must countersign it before the next stage starts.

| Stamp | Stage | What is produced | Produced by |
|---|---|---|---|
| 1 | Discover | Inventory record and risk tier | factory_core |
| 2 | Document | Current model documentation where every claim cites code lines, plus a list of differences against the old document | factory_core |
| 3 | Redevelop | Python rebuild of the SAS or R model, unit tests, four level parity certificate | redev_engine |
| 4 | Validate | Independent validation: discrimination, calibration, stability, fairness, findings, report | validation_lab (numbers) and factory_core (words) |
| 5 | Monitor | Drift monitoring on simulated production batches with an automatic revalidation trigger | validation_lab and factory_core |

Three design rules. Apply them in every design decision:

* Rule A, every claim is cited. Any sentence an LLM writes about a model must point to file and line evidence, and code checks that the evidence really exists. Unverified claims are flagged, never hidden.
* Rule B, every number is computed. No metric, coefficient or statistic ever comes from an LLM. Deterministic code computes the numbers. The LLM only writes words around them, and a checker confirms that every number in those words exists in the computed results.
* Rule C, every gate is signed. Agents never approve their own work. A human decision is recorded at each gate in a tamper evident audit trail. The person who approves validation cannot be the person who approved redevelopment.

## 3. Team, services and ownership

| Member | Service | Owns these paths (and nothing else) | Port |
|---|---|---|---|
| Varun | factory_core: agent orchestrator, inventory, documentation agents, governance API. Also integration lead. | `factory_core/`, `contracts/`, `docs/`, root files (`README.md`, `docker-compose.yml`, `.gitignore`, `.env.example`) | 8000 |
| Dhrishit | redev_engine: the sample legacy model estate, SAS and R to Python rebuild, parity proof. Also repository owner. | `redev_engine/`, `model_estate/` | 8001 |
| Harshit | validation_lab: validation metrics, fairness, monitoring, report rendering | `validation_lab/` | 8002 |
| Aayush | factory_console: the web dashboard | `factory_console/` | 5173 |

Repository: one shared GitHub repository, owned by Dhrishit. Each member works on a personal branch: `feat/factory_core`, `feat/redev_engine`, `feat/validation_lab`, `feat/factory_console`.

## 4. Rules that are not negotiable

1. Folder ownership. Each member creates and changes files only inside their own paths. A problem in someone else's area is reported to its owner, never fixed directly.
2. Manual commits. Each member commits and pushes their own folders by hand, with one plain line in the form `[service] what changed`.
3. Contracts are frozen. The JSON shapes in section 9 are the interface between services. Do not rename fields, change types or add required fields. Optional fields may be added only if they are listed in the service README under "Contract additions".
4. Work alone first. Every service must start and be demoable without the other services, using stub or sample data that follows the contract examples.
5. Data. Public or synthetic data only. No personal data. No real person names, use role titles such as "Head of Cards Credit Risk".
6. Secrets. Never hard code keys. Read them from environment variables. Never write a real key into any file. Keep `.env` out of the repository and provide `.env.example`.
7. Honesty. Never fake a result, a passing test or a parity match. If something fails, return the failure in the response and show it in the UI.
8. Paths. Every path inside a JSON payload is relative to the repository root and uses forward slashes.
9. Simple structure. Follow the file structure rules in section 6.1. The repository must be easy to navigate for someone who opens it for the first time.
10. Simple code. Small readable modules, type hints, docstrings, pinned dependencies. No clever abstractions.

## 5. Architecture

```
Browser: factory_console (React, port 5173)
   => factory_core (FastAPI, port 8000): REST API, agent pipeline with human gates, SQLite, audit trail
         => redev_engine (FastAPI, port 8001): POST /redevelop, POST /parity
         => validation_lab (FastAPI, port 8002): POST /validate, /report, /monitor/simulate, /monitor/run
         => LLM provider (OpenAI compatible endpoint, key from environment)
   redev_engine => LLM provider
   All Python services read model_estate/ and read or write artifacts/ on the same disk
   Optional: MLflow tracking server (port 5000) used by redev_engine and validation_lab
```

Facts about the architecture:

* Only factory_core talks to the browser. The frontend never calls redev_engine or validation_lab.
* validation_lab never calls an LLM. It is fully deterministic. This is deliberate (Rule B and validation independence).
* The LLM is used in two services only: factory_core (discovery, documentation, validation narrative) and redev_engine (code analysis, translation, test writing, diagnosis).
* Services exchange file paths, not file contents. Large outputs are written under `artifacts/` and referenced by path.

## 6. Repository layout

Every top level folder is one clearly named thing. The four services sit side by side at the top level.

```
EXL_P4_Hackathon/
  README.md            start here: what the project is, repository map, how to run it     Varun
  .env.example         every setting, each with a comment                                 Varun
  .gitignore                                                                              Varun
  docker-compose.yml   optional one command start                                         Varun
  docs/                project documents: PROJECT_CONTEXT.md, ARCHITECTURE.md, RESPONSIBLE_AI.md   Varun
  contracts/           example request and response for every API (read only for others)  Varun
  model_estate/        the sample bank: legacy models, data, golden outputs (read only for others)   Dhrishit
  factory_core/        service 1: orchestrator, agents, API for the dashboard             Varun
  redev_engine/        service 2: SAS and R to Python rebuild, parity proof               Dhrishit
  validation_lab/      service 3: validation, fairness, monitoring, report                Harshit
  factory_console/     service 4: web dashboard                                           Aayush
  artifacts/           run outputs, created at run time, ignored by git
```

### 6.1 File structure rules (apply to every folder)

The repository must be simple, easy to navigate and properly labelled.

1. Follow the folder map. Each service has a fixed folder map in its build plan. Do not add folders or files outside that map unless a step truly needs one. If you add one, give it a clear name and add it to the README folder map in the same step.
2. Stay shallow. At most two folder levels inside a service (for example `factory_core/app/agents/`). The frontend may use three under `src/`.
3. Names say what is inside. Full words, no abbreviations. Never use generic names such as `utils`, `helpers`, `misc`, `common`, `stuff`, `temp`, `new`, `final`, `v2`. Python files and folders use lowercase with underscores. React components use one component per file, and the file has the name of the component.
4. One purpose per file. If a file grows past about 300 lines, split it by purpose and give both parts clear names.
5. Label every file. Every source file starts with a short header (a docstring or comment of one to three lines) that says what the file does. Every function and class has a one line description.
6. Label every folder. Each service README has these sections in this order: "What this is", "Folder map", "How to run", "How to test", "Environment variables", "API". The folder map is a table with one row per folder and per important file, saying what it contains. Update it in the same step in which the structure changes. The root README has a "Repository map" with one line per top level folder.
7. Tests mirror the source. A module `app/parity_engine.py` is tested in `tests/test_parity_engine.py`.
8. Output stays out of source folders. Anything produced at run time goes under `artifacts/`, which git ignores. The only exceptions are `llm_cache/` in the two services that call the LLM and `model_estate/*/golden/`.
9. No leftovers. No unused files, backup copies, scratch scripts, commented out code blocks or empty folders.

## 7. The model estate (the sample bank)

`model_estate/` plays the role of the bank's legacy model landscape. Dhrishit builds it. Everyone else only reads it.

| Model id | Folder | Model | Language | Data | Stages it goes through |
|---|---|---|---|---|---|
| M001 | `M001_cc_pd_scorecard_sas` | Credit card probability of default scorecard (WoE logistic regression) | SAS | UCI "Default of Credit Card Clients" (30,000 rows, CC BY 4.0) | All five. This is the hero model. |
| M002 | `M002_loan_pd_glm_r` | Personal loan probability of default (binomial GLM) | R | UCI "Statlog German Credit Data" (1,000 rows, CC BY 4.0) | All five. Backup hero if SAS golden outputs are not available. |
| M003 | `M003_txn_fraud_gbm_py` | Card transaction fraud detector (gradient boosting) | Python | Synthetic, generated by a seeded script | Discover, Document, Validate, Monitor (no redevelopment needed) |
| M004 | `M004_risk_pricing_sas` | Risk based loan pricing (rules plus linear regression) | SAS | None | Discover, Document only |

Each model folder contains:

```
model_estate/M001_cc_pd_scorecard_sas/
  manifest.json                 technical pointers only (see below)
  code/                         legacy source files
  docs/                         the old, deliberately outdated model document
  data/dev.csv  data/oot.csv  data/data_dictionary.csv
  golden/scored_dev_legacy.csv  golden/scored_oot_legacy.csv  golden/coefficients_legacy.csv
```

Other estate files:

* `model_estate/estate_register.csv`: the bank's stale spreadsheet inventory. Columns: `model_id, model_name, business_line, model_owner, exposure_gbp_m, customer_facing, regulatory_use, last_code_change, doc_last_updated, last_validated, status`.
* `model_estate/_answer_keys/M00X.json`: ground truth used only by evaluation scripts (expected inventory fields and the list of seeded document discrepancies). Agents must never read this folder and the file API must block it.
* `model_estate/_tools/`: scripts that download and prepare data and regenerate golden outputs.

Example file: `contracts/examples/estate_manifest.M001.json` (also stored as `model_estate/M001_cc_pd_scorecard_sas/manifest.json`). Paths inside a manifest are relative to the model folder.

```json
{
  "model_id": "M001",
  "folder": "model_estate/M001_cc_pd_scorecard_sas",
  "language": "SAS",
  "code_files": ["code/01_prepare.sas", "code/02_train.sas", "code/03_score.sas"],
  "doc_files": ["docs/model_document_2021.md"],
  "data": {
    "dev_path": "data/dev.csv",
    "oot_path": "data/oot.csv",
    "dictionary_path": "data/data_dictionary.csv",
    "id_col": "ID",
    "target_col": "default_flag",
    "protected_cols": ["SEX", "AGE_BAND"]
  },
  "golden": {
    "scored_dev_path": "golden/scored_dev_legacy.csv",
    "scored_oot_path": "golden/scored_oot_legacy.csv",
    "coefficients_path": "golden/coefficients_legacy.csv",
    "produced_by": "SAS OnDemand for Academics",
    "produced_on": "2026-11-15"
  },
  "redevelop": true
}
```

Conventions:

* `data` is `null` when a model has no data (M004). `golden` is `null` when no legacy outputs exist.
* Scored files, legacy or rebuilt, always have exactly these columns: `ID, pd, score, decision`. `pd` is the probability of the bad event between 0 and 1. `score` is an integer where higher means lower risk (use 0 when a model has no score). `decision` is `APPROVE` or `DECLINE` (for the fraud model `APPROVE` means the transaction is allowed).
* `coefficients_legacy.csv` has columns `variable, estimate`.
* The "oot" sample for M001 and M002 is a random holdout, because these public datasets have no usable time dimension. We name it `oot` for pipeline consistency and state this limitation honestly in documents and in the UI ("holdout sample").
* Protected attributes (`SEX`, `AGE_BAND`) are never model inputs. They are kept in the data only so that fairness can be tested.

## 8. Stages, statuses and gates

Stage names: `discover`, `document`, `redevelop`, `validate`, `monitor`.

Stage status values: `PENDING`, `RUNNING`, `AWAITING_REVIEW`, `APPROVED`, `REJECTED`, `FAILED`, `SKIPPED`.

Run status values: `RUNNING`, `AWAITING_REVIEW`, `COMPLETED`, `REJECTED`, `FAILED`.

Flow for one run: a stage runs, its output is stored, the stage moves to `AWAITING_REVIEW`, a human approves or rejects through the UI, and only then does the next stage start. A stage that does not apply to a model is `SKIPPED` with a reason (for example redevelopment for a model that is already Python).

Other shared enumerations:

* `model_type`: `credit_pd`, `fraud`, `pricing`, `other`
* `language`: `SAS`, `R`, `Python`
* `tier`: `Tier 1`, `Tier 2`, `Tier 3`
* `doc_status`: `MISSING`, `OUTDATED`, `CURRENT`
* ratings: `GREEN`, `AMBER`, `RED`
* finding severity: `HIGH`, `MEDIUM`, `LOW`
* reviewer role: `developer`, `validator`, `owner`

All timestamps are ISO 8601 strings in UTC.

## 9. Contracts

Shared conventions for every service:

* `GET /health` returns `{"status": "ok", "service": "<service name>", "version": "0.1.0"}`.
* Errors use the HTTP status code plus the body `{"error": {"code": "SOME_CODE", "message": "human readable text"}}`.
* All example values below are illustrative sample values so that everyone codes against the same shapes. They are not real results and must never be copied into the deck.
* Include convention in example files: an object of the form `{"$include": "some_file.json"}` means that the full content of that other example file belongs at that place. Resolve it when you create example or mock files. It is never sent over the wire.

### 9.1 redev_engine (port 8001, called by factory_core only)

| Method and path | Purpose |
|---|---|
| `POST /redevelop` | Run the full rebuild for one model: analyse, translate, write tests, run tests, check parity, self heal, issue certificate. Synchronous, can take minutes. |
| `POST /parity` | Re run only the deterministic parity check for a model that already has a rebuilt `model.py`. Body: `{"model_id": "M001", "estate_path": "model_estate/M001_cc_pd_scorecard_sas"}`. Returns the `parity` object. |
| `GET /pitfalls` | The translation pitfall library: `{"pitfalls": [{"id": "SAS_MISSING_COMPARE", "language": "SAS", "title": "...", "description": "...", "python_fix": "..."}]}` |

Example file: `contracts/examples/redevelop_request.json`

```json
{
  "run_id": "run_M001_001",
  "model_id": "M001",
  "estate_path": "model_estate/M001_cc_pd_scorecard_sas",
  "max_heal_iterations": 3,
  "use_pitfall_library": true
}
```

Example file: `contracts/examples/redevelop_result.M001.json`

```json
{
  "model_id": "M001",
  "run_id": "run_M001_001",
  "status": "PARITY_PASSED",
  "source_language": "SAS",
  "target_language": "Python",
  "iterations": [
    {
      "iteration": 1,
      "unit_tests_passed": 12,
      "unit_tests_failed": 2,
      "parity_passed": false,
      "max_abs_diff_pd": 0.4127,
      "diagnosis": "All mismatched records have BILL_AMT2 equal to 0. SAS returns missing for division by zero and a missing value compares as smaller than any number, so these records fall in the first bin.",
      "fix_applied": "Treat division by zero as missing and send missing values to the first bin, as SAS does."
    },
    {
      "iteration": 2,
      "unit_tests_passed": 14,
      "unit_tests_failed": 0,
      "parity_passed": true,
      "max_abs_diff_pd": 3.1e-9,
      "diagnosis": null,
      "fix_applied": null
    }
  ],
  "generated_files": [
    {"path": "artifacts/M001/redevelop/model.py", "kind": "model_code"},
    {"path": "artifacts/M001/redevelop/test_model.py", "kind": "unit_tests"},
    {"path": "artifacts/M001/redevelop/logic_spec.json", "kind": "logic_spec"},
    {"path": "artifacts/M001/redevelop/translation_notes.md", "kind": "notes"},
    {"path": "artifacts/M001/redevelop/scored_dev.csv", "kind": "scores_dev"},
    {"path": "artifacts/M001/redevelop/scored_oot.csv", "kind": "scores_oot"}
  ],
  "line_mapping": [
    {
      "legacy_file": "model_estate/M001_cc_pd_scorecard_sas/code/01_prepare.sas",
      "legacy_start": 22,
      "legacy_end": 31,
      "python_file": "artifacts/M001/redevelop/model.py",
      "python_start": 40,
      "python_end": 52,
      "note": "WoE binning of utilisation"
    }
  ],
  "unit_tests": {"total": 14, "passed": 14, "failed": 0},
  "parity": {
    "passed": true,
    "records_compared": 30000,
    "tolerance_pd": 1e-6,
    "tolerance_coef": 1e-4,
    "levels": [
      {"level": "L1_coefficients", "status": "PASSED", "max_abs_diff": 2.2e-6, "mismatched_records": null, "match_rate": null, "psi": null, "detail": "9 of 9 refitted coefficients within tolerance of the legacy estimates"},
      {"level": "L2_record_scores", "status": "PASSED", "max_abs_diff": 3.1e-9, "mismatched_records": 0, "match_rate": 1.0, "psi": null, "detail": "PD compared record by record on dev and oot"},
      {"level": "L3_decisions", "status": "PASSED", "max_abs_diff": 0, "mismatched_records": 0, "match_rate": 1.0, "psi": null, "detail": "Score points and approve or decline decision identical"},
      {"level": "L4_distribution", "status": "PASSED", "max_abs_diff": null, "mismatched_records": null, "match_rate": null, "psi": 0.0, "detail": "Score distribution identical across 10 bins"}
    ],
    "hashes": {
      "legacy_code_sha256": "9f2c...",
      "python_code_sha256": "41ab...",
      "input_data_sha256": "c07e...",
      "golden_output_sha256": "5d90..."
    },
    "certificate_md_path": "artifacts/M001/redevelop/parity_certificate.md",
    "certificate_json_path": "artifacts/M001/redevelop/parity_certificate.json",
    "mismatch_sample_path": null
  },
  "pitfalls_checked": ["SAS_MISSING_COMPARE", "SAS_DIVIDE_BY_ZERO", "LOGISTIC_EVENT_LEVEL", "ROUND_HALF_AWAY", "REGULARISATION_DEFAULT"],
  "mlflow": null,
  "llm_trace": [
    {"step": "analyze", "model": "provider/model-id", "prompt_sha256": "ab12...", "input_tokens": 5210, "output_tokens": 1830, "latency_ms": 9100, "cached": false}
  ],
  "duration_seconds": 96.4,
  "error": null
}
```

Field notes:

* `status` is one of `PARITY_PASSED`, `PARITY_FAILED`, `TRANSLATED_NO_GOLDEN` (code translated and unit tested but no legacy outputs exist to compare against), `ERROR`.
* Parity level `status` is one of `PASSED`, `FAILED`, `NOT_APPLICABLE`.
* `parity.passed` is true only when every applicable level passed.
* The rebuilt model is always written to `artifacts/{model_id}/redevelop/model.py` and exposes `prepare(df)`, `score(df)` returning a DataFrame with columns `ID, pd, score, decision`, and where estimation applies `fit(dev_df)`.

### 9.2 validation_lab (port 8002, called by factory_core only)

| Method and path | Purpose |
|---|---|
| `POST /validate` | Run every validation test for one model and return a ValidationResult |
| `POST /report` | Render the validation report (HTML, optionally DOCX) from a stored ValidationResult plus narrative text supplied by factory_core |
| `POST /monitor/simulate` | Create simulated production batches with injected drift |
| `POST /monitor/run` | Compute drift and performance per batch and decide whether revalidation is triggered |

Example file: `contracts/examples/validate_request.json`

```json
{
  "run_id": "run_M001_001",
  "model_id": "M001",
  "model_type": "credit_pd",
  "data": {
    "dev_path": "model_estate/M001_cc_pd_scorecard_sas/data/dev.csv",
    "oot_path": "model_estate/M001_cc_pd_scorecard_sas/data/oot.csv",
    "id_col": "ID",
    "target_col": "default_flag"
  },
  "scores": {
    "dev_path": "artifacts/M001/redevelop/scored_dev.csv",
    "oot_path": "artifacts/M001/redevelop/scored_oot.csv",
    "pd_col": "pd",
    "score_col": "score",
    "decision_col": "decision"
  },
  "feature_cols": ["PAY_0", "LIMIT_BAL", "BILL_AMT1", "PAY_AMT1"],
  "protected_cols": ["SEX", "AGE_BAND"],
  "model_module_path": "artifacts/M001/redevelop/model.py",
  "thresholds": null
}
```

Example file: `contracts/examples/validation_result.M001.json`

```json
{
  "model_id": "M001",
  "run_id": "run_M001_001",
  "status": "COMPLETED",
  "overall_rating": "AMBER",
  "sample_sizes": {"dev": 21000, "oot": 9000},
  "sections": {
    "data_quality": {
      "rating": "GREEN",
      "checks": [
        {"check": "missing_rate_max", "value": 0.0, "threshold": 0.05, "passed": true},
        {"check": "duplicate_ids", "value": 0, "threshold": 0, "passed": true}
      ],
      "target_rate": {"dev": 0.2212, "oot": 0.2219}
    },
    "discrimination": {
      "rating": "GREEN",
      "dev": {"auc": 0.771, "gini": 0.542, "ks": 0.412},
      "oot": {"auc": 0.764, "gini": 0.528, "ks": 0.401},
      "gini_relative_drop": 0.026
    },
    "calibration": {
      "rating": "AMBER",
      "oot": {
        "brier": 0.141,
        "mean_predicted_pd": 0.2087,
        "observed_default_rate": 0.2219,
        "observed_over_expected": 1.063,
        "hosmer_lemeshow_stat": 21.7,
        "hosmer_lemeshow_p": 0.0055
      },
      "decile_table": [
        {"decile": 1, "n": 900, "mean_pd": 0.041, "observed_rate": 0.047}
      ]
    },
    "stability": {
      "rating": "GREEN",
      "psi_score": 0.012,
      "csi": [
        {"feature": "PAY_0", "csi": 0.004, "rating": "GREEN"}
      ]
    },
    "backtest": {
      "rating": "GREEN",
      "bands": [
        {"band": "A", "pd_min": 0.0, "pd_max": 0.082, "n": 1800, "mean_pd": 0.05, "observed_rate": 0.054, "binomial_p": 0.41, "light": "GREEN"}
      ]
    },
    "fairness": {
      "rating": "GREEN",
      "favourable_outcome": "APPROVE",
      "by_attribute": [
        {
          "attribute": "SEX",
          "groups": [
            {"group": "1", "n": 3560, "approval_rate": 0.71, "approval_rate_good_customers": 0.80, "approval_rate_bad_customers": 0.39, "observed_default_rate": 0.24, "mean_pd": 0.23},
            {"group": "2", "n": 5440, "approval_rate": 0.76, "approval_rate_good_customers": 0.83, "approval_rate_bad_customers": 0.43, "observed_default_rate": 0.21, "mean_pd": 0.20}
          ],
          "demographic_parity_ratio": 0.934,
          "equal_opportunity_diff": 0.03,
          "equalized_odds_diff": 0.04,
          "rating": "GREEN"
        }
      ]
    },
    "sensitivity": {
      "rating": "GREEN",
      "shocks": [
        {"feature": "LIMIT_BAL", "shock": "plus 10 percent", "mean_pd_change": -0.0021, "decision_flip_rate": 0.004}
      ]
    },
    "benchmark": {
      "rating": "GREEN",
      "challenger": "gradient_boosting",
      "champion_auc_oot": 0.764,
      "challenger_auc_oot": 0.779,
      "auc_uplift": 0.015
    }
  },
  "findings": [
    {
      "id": "F001",
      "section": "calibration",
      "severity": "MEDIUM",
      "title": "Hosmer Lemeshow test rejects calibration on the holdout sample",
      "detail": "The Hosmer Lemeshow p value is below 0.05 although observed over expected is within tolerance.",
      "evidence": {"metric": "hosmer_lemeshow_p", "value": 0.0055, "threshold": "0.05 or above is green"},
      "recommendation": "Review calibration by decile and consider recalibrating the intercept on recent data."
    }
  ],
  "charts": [
    {"id": "roc_oot", "title": "ROC curve, holdout", "path": "artifacts/M001/validation/charts/roc_oot.png"},
    {"id": "calibration_oot", "title": "Calibration by decile, holdout", "path": "artifacts/M001/validation/charts/calibration_oot.png"},
    {"id": "score_distribution", "title": "Model output distribution, development against holdout", "path": "artifacts/M001/validation/charts/score_distribution.png"},
    {"id": "fairness_SEX", "title": "Approval rate by SEX", "path": "artifacts/M001/validation/charts/fairness_SEX.png"}
  ],
  "series": {
    "roc_oot": [{"fpr": 0.0, "tpr": 0.0}, {"fpr": 0.1, "tpr": 0.42}, {"fpr": 1.0, "tpr": 1.0}],
    "calibration_oot": [{"decile": 1, "mean_pd": 0.041, "observed_rate": 0.047}],
    "score_distribution": [{"bin": "D01", "dev_share": 0.10, "oot_share": 0.097}]
  },
  "thresholds_used": {
    "auc_green": 0.70, "auc_amber": 0.60,
    "ks_green": 0.30, "ks_amber": 0.20,
    "gini_drop_green": 0.10, "gini_drop_amber": 0.20,
    "oe_band_green": 0.10, "oe_band_amber": 0.20,
    "hl_p_green": 0.05,
    "psi_green": 0.10, "psi_amber": 0.25,
    "dp_ratio_green": 0.80, "dp_ratio_amber": 0.70,
    "eo_diff_green": 0.05, "eo_diff_amber": 0.10,
    "benchmark_uplift_amber": 0.03
  },
  "result_path": "artifacts/M001/validation/result.json",
  "duration_seconds": 14.2,
  "error": null
}
```

Field notes:

* Fairness definitions. Favourable outcome is `APPROVE`. A good customer is one whose target is 0. `demographic_parity_ratio` is the lowest group approval rate divided by the highest. `equal_opportunity_diff` is the largest gap between groups in approval rate among good customers. `equalized_odds_diff` is the larger of that gap and the gap in approval rate among bad customers.
* `overall_rating` is `RED` if any finding is `HIGH`, `AMBER` if any finding is `MEDIUM`, otherwise `GREEN`.
* `sensitivity` and `benchmark` may be `null` when they cannot be computed (for example no `model_module_path`).
* `psi_score`, the back test bands and the `score_distribution` series are computed on `pd`, the model output, with bin edges taken from the development sample (deciles named D01 to D10 for the distribution, quintile bands A to E for the back test, A being the lowest PD). This works for every model type, including models that have no scorecard points.
* Thresholds are illustrative defaults for the demo, not regulatory limits. The report must say so.

Example file: `contracts/examples/report_request.json`

```json
{
  "run_id": "run_M001_001",
  "model_id": "M001",
  "validation_result_path": "artifacts/M001/validation/result.json",
  "inventory_record": {"$include": "inventory_record.M001.json"},
  "parity_summary": {
    "status": "PARITY_PASSED",
    "records_compared": 30000,
    "max_abs_diff_pd": 3.1e-9,
    "decision_match_rate": 1.0,
    "certificate_md_path": "artifacts/M001/redevelop/parity_certificate.md"
  },
  "narrative": {
    "executive_summary": "markdown text written by the validator agent",
    "conceptual_soundness": "markdown text",
    "findings_commentary": "markdown text",
    "conclusion": "markdown text",
    "unverified_numbers": []
  },
  "sign_off": {"validator_agent_model": "provider/model-id", "human_validator": null, "signed_at": null},
  "formats": ["html", "docx"]
}
```

`inventory_record` is the full InventoryRecord from section 9.3. `parity_summary` is `null` for models that were not redeveloped. Response:

```json
{
  "model_id": "M001",
  "html_path": "artifacts/M001/validation/validation_report.html",
  "docx_path": "artifacts/M001/validation/validation_report.docx",
  "error": null
}
```

Example file: `contracts/examples/monitor_simulate_request.json`

```json
{
  "model_id": "M001",
  "data_path": "model_estate/M001_cc_pd_scorecard_sas/data/oot.csv",
  "scores_path": "artifacts/M001/redevelop/scored_oot.csv",
  "id_col": "ID",
  "target_col": "default_flag",
  "pd_col": "pd",
  "score_col": "score",
  "feature_cols": ["PAY_0", "LIMIT_BAL", "BILL_AMT1", "PAY_AMT1"],
  "n_batches": 6,
  "batch_size": 3000,
  "drift_start_batch": 4,
  "drift_strength": 0.5,
  "seed": 42
}
```

Response: `{"model_id": "M001", "simulated": true, "batches_dir": "artifacts/M001/monitoring/batches", "batches": [{"batch": "2026_01", "path": "artifacts/M001/monitoring/batches/batch_2026_01.csv", "n": 3000, "drift_injected": false}], "error": null}`

Example file: `contracts/examples/monitor_run_request.json`

```json
{
  "model_id": "M001",
  "reference": {
    "data_path": "model_estate/M001_cc_pd_scorecard_sas/data/dev.csv",
    "scores_path": "artifacts/M001/redevelop/scored_dev.csv"
  },
  "batches_dir": "artifacts/M001/monitoring/batches",
  "id_col": "ID",
  "target_col": "default_flag",
  "pd_col": "pd",
  "score_col": "score",
  "feature_cols": ["PAY_0", "LIMIT_BAL", "BILL_AMT1", "PAY_AMT1"],
  "thresholds": null
}
```

Example file: `contracts/examples/monitoring_result.M001.json`

```json
{
  "model_id": "M001",
  "status": "COMPLETED",
  "simulated": true,
  "reference_sample": "dev",
  "batches": [
    {"batch": "2026_01", "n": 3000, "psi_score": 0.011, "max_csi": {"feature": "PAY_0", "csi": 0.009}, "auc": 0.765, "observed_default_rate": 0.220, "mean_pd": 0.209, "alert": "GREEN"},
    {"batch": "2026_04", "n": 3000, "psi_score": 0.134, "max_csi": {"feature": "PAY_0", "csi": 0.171}, "auc": 0.752, "observed_default_rate": 0.251, "mean_pd": 0.233, "alert": "AMBER"},
    {"batch": "2026_05", "n": 3000, "psi_score": 0.291, "max_csi": {"feature": "PAY_0", "csi": 0.334}, "auc": 0.731, "observed_default_rate": 0.297, "mean_pd": 0.262, "alert": "RED"}
  ],
  "alerts": [
    {"batch": "2026_05", "level": "RED", "rule": "score PSI above 0.25", "value": 0.291}
  ],
  "revalidation_triggered": true,
  "trigger_reason": "Score PSI above 0.25 in batch 2026_05",
  "thresholds_used": {"psi_green": 0.10, "psi_amber": 0.25, "auc_drop_trigger": 0.05},
  "result_path": "artifacts/M001/monitoring/result.json",
  "error": null
}
```

### 9.3 factory_core public API (port 8000, called by the frontend)

| Method and path | Returns |
|---|---|
| `GET /api/models` | `{"models": [ModelSummary]}` |
| `POST /api/estate/scan` | Registers every model folder found in `model_estate/` (no LLM). Returns `{"models_found": ["M001", "M002", "M003", "M004"]}` |
| `GET /api/models/{model_id}` | InventoryRecord |
| `POST /api/models/{model_id}/runs` | Starts a run. Body `{"stages": ["discover", "document", "redevelop", "validate", "monitor"], "auto_approve": false}`. Returns `{"run_id": "run_M001_001"}` |
| `GET /api/runs/{run_id}` | Run |
| `POST /api/runs/{run_id}/gates/{stage}/decision` | Body GateDecision. Returns the updated Run. Returns 409 with code `INDEPENDENCE_VIOLATION` when the validate gate is approved by the reviewer who approved the redevelop gate. |
| `GET /api/models/{model_id}/documentation` | Documentation |
| `GET /api/models/{model_id}/redevelopment` | RedevelopResult exactly as in section 9.1 |
| `GET /api/models/{model_id}/validation` | ValidationView |
| `GET /api/models/{model_id}/monitoring` | MonitoringResult exactly as in section 9.2 |
| `GET /api/models/{model_id}/compliance` | Compliance |
| `GET /api/audit?model_id=M001&limit=200` | Audit |
| `GET /api/metrics/factory` | FactoryMetrics |
| `GET /api/files?path=...` | FileView. Text content of one file under `model_estate/` or `artifacts/`. Blocks `_answer_keys`. |
| `GET /api/artifacts/{path}` | Streams a binary artifact (png, html, docx) |

A result endpoint returns 404 with code `NOT_AVAILABLE` when that stage has not produced output yet.

Example file: `contracts/examples/models_list.json`

```json
{
  "models": [
    {
      "model_id": "M001",
      "model_name": "Credit Card PD Scorecard",
      "model_type": "credit_pd",
      "language": "SAS",
      "algorithm": "Logistic regression scorecard on WoE variables",
      "business_line": "Cards",
      "tier": "Tier 1",
      "doc_status": "OUTDATED",
      "last_validated": "2023-02-14",
      "pipeline_status": {"discover": "APPROVED", "document": "AWAITING_REVIEW", "redevelop": "PENDING", "validate": "PENDING", "monitor": "PENDING"},
      "overall_rating": null,
      "revalidation_required": false,
      "active_run_id": "run_M001_001"
    }
  ]
}
```

Example file: `contracts/examples/inventory_record.M001.json`

```json
{
  "model_id": "M001",
  "model_name": "Credit Card PD Scorecard",
  "model_type": "credit_pd",
  "purpose": "Estimates the probability that a credit card customer defaults next month. Used for approve or decline decisions.",
  "business_line": "Cards",
  "model_owner": "Head of Cards Credit Risk",
  "language": "SAS",
  "algorithm": "Logistic regression scorecard on WoE variables",
  "target_variable": "default_flag",
  "input_variables": [
    {"name": "PAY_0", "description": "Repayment status in the most recent month", "transformation": "WoE bins"}
  ],
  "outputs": ["pd", "score", "decision"],
  "upstream_dependencies": [],
  "downstream_uses": ["Credit card approve or decline decision"],
  "exposure_gbp_m": 1850,
  "regulatory_use": "IRB",
  "customer_facing": true,
  "tiering": {
    "tier": "Tier 1",
    "materiality_score": 3,
    "complexity_score": 1,
    "rationale": ["Exposure above GBP 1bn", "Used for regulatory capital", "Customer facing credit decision"]
  },
  "doc_status": "OUTDATED",
  "doc_last_updated": "2021-03-01",
  "last_code_change": "2023-06-20",
  "last_validated": "2023-02-14",
  "next_validation_due": "2024-02-14",
  "source_files": [
    {"path": "model_estate/M001_cc_pd_scorecard_sas/code/01_prepare.sas", "kind": "code", "lines": 120, "sha256": "9f2c..."}
  ],
  "field_evidence": {
    "algorithm": {"file": "model_estate/M001_cc_pd_scorecard_sas/code/02_train.sas", "start_line": 12, "end_line": 19, "quote": "proc logistic data=work.dev_woe descending;", "status": "VERIFIED"}
  },
  "open_questions": ["Who approved the 2023 change to the cutoff?"],
  "pipeline_status": {"discover": "APPROVED", "document": "AWAITING_REVIEW", "redevelop": "PENDING", "validate": "PENDING", "monitor": "PENDING"},
  "revalidation_required": false,
  "created_at": "2026-11-15T10:02:11Z",
  "updated_at": "2026-11-15T10:05:40Z"
}
```

Example file: `contracts/examples/run.json`

```json
{
  "run_id": "run_M001_001",
  "model_id": "M001",
  "status": "AWAITING_REVIEW",
  "current_stage": "document",
  "auto_approve": false,
  "stages": [
    {
      "stage": "discover",
      "status": "APPROVED",
      "started_at": "2026-11-15T10:02:11Z",
      "finished_at": "2026-11-15T10:02:33Z",
      "duration_seconds": 21.4,
      "summary": "Inventory record created. Tier 1.",
      "skip_reason": null,
      "error": null,
      "gate": {"decision": "approve", "reviewer": "varun", "role": "owner", "comment": "Looks right", "decided_at": "2026-11-15T10:04:02Z", "review_seconds": 89}
    },
    {
      "stage": "document",
      "status": "AWAITING_REVIEW",
      "started_at": "2026-11-15T10:04:03Z",
      "finished_at": "2026-11-15T10:05:40Z",
      "duration_seconds": 97.0,
      "summary": "10 sections, 42 claims, 40 verified. 4 differences against the 2021 document.",
      "skip_reason": null,
      "error": null,
      "gate": null
    },
    {"stage": "redevelop", "status": "PENDING", "started_at": null, "finished_at": null, "duration_seconds": null, "summary": null, "skip_reason": null, "error": null, "gate": null},
    {"stage": "validate", "status": "PENDING", "started_at": null, "finished_at": null, "duration_seconds": null, "summary": null, "skip_reason": null, "error": null, "gate": null},
    {"stage": "monitor", "status": "PENDING", "started_at": null, "finished_at": null, "duration_seconds": null, "summary": null, "skip_reason": null, "error": null, "gate": null}
  ],
  "started_at": "2026-11-15T10:02:11Z",
  "finished_at": null,
  "total_agent_seconds": 118.4,
  "total_review_seconds": 89
}
```

Example file: `contracts/examples/gate_decision_request.json`

```json
{
  "decision": "approve",
  "reviewer": "harshit",
  "role": "validator",
  "comment": "Findings are reasonable. Calibration to be reviewed next quarter."
}
```

`decision` is `approve` or `reject`. A reject sets the stage and the run to `REJECTED` and stores the comment.

Example file: `contracts/examples/documentation.M001.json`

```json
{
  "model_id": "M001",
  "generated_at": "2026-11-15T10:05:40Z",
  "generated_by_model": "provider/model-id",
  "groundedness": {"claims_total": 42, "claims_verified": 40, "claims_unverified": 1, "claims_sme_input_needed": 1, "score": 0.952},
  "sections": [
    {
      "id": "methodology",
      "title": "Methodology",
      "markdown": "The model is a logistic regression fitted on eight WoE transformed variables [C014].",
      "claims": [
        {
          "id": "C014",
          "text": "The model is a logistic regression fitted on eight WoE transformed variables.",
          "status": "VERIFIED",
          "evidence": [
            {"file": "model_estate/M001_cc_pd_scorecard_sas/code/02_train.sas", "start_line": 12, "end_line": 19, "quote": "proc logistic data=work.dev_woe descending;"}
          ]
        }
      ]
    }
  ],
  "doc_drift": [
    {
      "id": "D001",
      "severity": "HIGH",
      "topic": "Decision cutoff",
      "legacy_doc_says": "Applications scoring below 520 are declined.",
      "code_says": "The cutoff in the scoring code is 540.",
      "legacy_evidence": {"file": "model_estate/M001_cc_pd_scorecard_sas/docs/model_document_2021.md", "start_line": 88, "end_line": 88, "quote": "below 520 are declined"},
      "code_evidence": {"file": "model_estate/M001_cc_pd_scorecard_sas/code/03_score.sas", "start_line": 41, "end_line": 41, "quote": "if score < 540 then decision = 'DECLINE';"},
      "status": "VERIFIED"
    }
  ],
  "markdown_path": "artifacts/M001/document/model_document.md"
}
```

Claim `status` is `VERIFIED` (the quoted text was found at the cited lines by code), `UNVERIFIED` (evidence given but not found) or `SME_INPUT_NEEDED` (no evidence exists in the files, a human must answer). Section ids, in order: `overview`, `intended_use`, `data_and_variables`, `methodology`, `model_specification`, `assumptions`, `limitations`, `implementation_and_controls`, `monitoring_plan`, `change_log`.

Example file: `contracts/examples/validation_view.M001.json`

```json
{
  "model_id": "M001",
  "result": {"$include": "validation_result.M001.json"},
  "narrative": {
    "executive_summary": "markdown text",
    "conceptual_soundness": "markdown text",
    "findings_commentary": "markdown text",
    "conclusion": "markdown text",
    "unverified_numbers": []
  },
  "number_grounding": {"numbers_in_narrative": 31, "numbers_verified": 31, "score": 1.0},
  "validator_agent_model": "provider/model-id",
  "report": {
    "html_path": "artifacts/M001/validation/validation_report.html",
    "docx_path": "artifacts/M001/validation/validation_report.docx"
  }
}
```

Example file: `contracts/examples/compliance.M001.json`

```json
{
  "model_id": "M001",
  "disclaimer": "Simplified team mapping to the five SS1/23 principles for demonstration. Not a legal or regulatory assessment.",
  "principles": [
    {
      "principle": "P1",
      "title": "Model identification and model risk classification",
      "items": [
        {"id": "P1_inventory", "expectation": "The model is recorded in the inventory with owner, purpose and dependencies", "status": "MET", "evidence_path": "artifacts/M001/discover/inventory_record.json", "note": null},
        {"id": "P1_tiering", "expectation": "A risk tier is assigned from materiality and complexity", "status": "MET", "evidence_path": "artifacts/M001/discover/inventory_record.json", "note": null}
      ]
    },
    {
      "principle": "P2",
      "title": "Governance",
      "items": [
        {"id": "P2_board", "expectation": "Board and senior management oversight of the framework", "status": "OUT_OF_SCOPE", "evidence_path": null, "note": "Organisational control, outside a prototype"}
      ]
    }
  ],
  "coverage": {"met": 11, "partial": 2, "not_met": 1, "out_of_scope": 4}
}
```

Item `status` is `MET`, `PARTIAL`, `NOT_MET` or `OUT_OF_SCOPE`. The five principle titles are: P1 Model identification and model risk classification, P2 Governance, P3 Model development, implementation and use, P4 Independent model validation, P5 Model risk mitigants.

Example file: `contracts/examples/audit.json`

```json
{
  "chain_valid": true,
  "events": [
    {
      "seq": 17,
      "ts": "2026-11-15T10:04:02Z",
      "model_id": "M001",
      "run_id": "run_M001_001",
      "stage": "discover",
      "actor_type": "human",
      "actor": "varun",
      "action": "gate_decision",
      "detail": {"decision": "approve", "role": "owner", "comment": "Looks right"},
      "prev_hash": "77aa...",
      "hash": "c3d1..."
    },
    {
      "seq": 18,
      "ts": "2026-11-15T10:04:09Z",
      "model_id": "M001",
      "run_id": "run_M001_001",
      "stage": "document",
      "actor_type": "agent",
      "actor": "documentation_agent",
      "action": "llm_call",
      "detail": {"step": "section:methodology", "model": "provider/model-id", "prompt_sha256": "ab12...", "input_tokens": 6120, "output_tokens": 940, "latency_ms": 7400, "cached": false},
      "prev_hash": "c3d1...",
      "hash": "09be..."
    }
  ]
}
```

`actor_type` is `agent`, `human` or `system`. `action` is one of `stage_started`, `stage_completed`, `stage_failed`, `stage_skipped`, `llm_call`, `tool_call`, `service_call`, `artifact_written`, `gate_decision`, `revalidation_triggered`. Each event hash is the SHA 256 of the previous hash plus the canonical JSON of the event, which makes the trail tamper evident.

Example file: `contracts/examples/factory_metrics.json`

```json
{
  "models_total": 4,
  "by_tier": {"Tier 1": 2, "Tier 2": 1, "Tier 3": 1},
  "by_language": {"SAS": 2, "R": 1, "Python": 1},
  "docs_outdated_at_discovery": 4,
  "docs_generated": 4,
  "avg_groundedness": 0.95,
  "parity_certificates_issued": 1,
  "validations_completed": 3,
  "open_findings": {"HIGH": 0, "MEDIUM": 3, "LOW": 2},
  "revalidation_triggers": 1,
  "avg_agent_minutes_per_model": 6.2,
  "human_review_minutes_logged": 38,
  "manual_baseline_weeks_per_validation": [8, 12]
}
```

Example file: `contracts/examples/file_view.json`

```json
{
  "path": "model_estate/M001_cc_pd_scorecard_sas/code/02_train.sas",
  "language": "sas",
  "lines": 44,
  "content": "/* 02_train.sas */\nproc logistic data=work.dev_woe descending;\n  model default_flag = woe_pay0 woe_util;\nrun;\n"
}
```

### 9.4 Static snapshot layout (P1, used for the deployed demo link)

factory_core has a script that saves the real response of every GET endpoint to JSON files. The frontend in `snapshot` mode reads these files instead of calling the API, so the deployed link needs no backend. Layout, relative to the snapshot folder that Aayush copies into `factory_console/public/snapshot/`:

```
models.json                                  GET /api/models
metrics.json                                 GET /api/metrics/factory
audit.json                                   GET /api/audit
models/{model_id}.json                       GET /api/models/{model_id}
models/{model_id}/documentation.json
models/{model_id}/redevelopment.json
models/{model_id}/validation.json
models/{model_id}/monitoring.json
models/{model_id}/compliance.json
runs/{run_id}.json                           GET /api/runs/{run_id}
files/{path with every slash replaced by two underscores}.json     GET /api/files?path=...
artifacts/{same relative path as under artifacts/}                 charts and reports
```

A missing file means the endpoint returned `NOT_AVAILABLE` for that model. In snapshot mode the UI is read only: gate buttons are disabled and a banner says "Recorded run".

## 10. Where files are written

```
artifacts/{model_id}/discover/inventory_record.json
artifacts/{model_id}/document/model_document.json   model_document.md   doc_drift.json
artifacts/{model_id}/redevelop/model.py   test_model.py   logic_spec.json   translation_notes.md
artifacts/{model_id}/redevelop/scored_dev.csv   scored_oot.csv   parity_certificate.md   parity_certificate.json   result.json
artifacts/{model_id}/validation/result.json   charts/*.png   validation_report.html   validation_report.docx
artifacts/{model_id}/monitoring/batches/batch_*.csv   result.json
artifacts/{model_id}/compliance/ss123_matrix.json
```

Scores used for validation: for a redeveloped model use `artifacts/{model_id}/redevelop/scored_*.csv`. For a model that was not redeveloped use the golden files from the estate.

## 11. Environment variables and ports

One `.env` file at the repository root (never committed). Python services load it from the repository root. Example file `.env.example`:

```
# LLM, any OpenAI compatible endpoint. Used by factory_core and redev_engine only.
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_API_KEY=
LLM_MODEL=
LLM_MODEL_VALIDATOR=
LLM_MODE=live
LLM_TEMPERATURE=0

# Service addresses
FACTORY_CORE_URL=http://localhost:8000
REDEV_ENGINE_URL=http://localhost:8001
VALIDATION_LAB_URL=http://localhost:8002
USE_STUBS=false

# Paths, relative to the repository root
ESTATE_DIR=model_estate
ARTIFACTS_DIR=artifacts

# Optional
MLFLOW_TRACKING_URI=
```

Notes:

* The running application needs its own LLM API key. The default plan is a free tier key from Google AI Studio used through its OpenAI compatible endpoint, with a current Gemini Flash model id placed in `LLM_MODEL`. Any OpenAI compatible provider works by changing `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` (Groq, OpenRouter, an Azure deployment, or a local Ollama server at `http://localhost:11434/v1`).
* Model ids change often. On 14 November 2026 Google's own examples for the OpenAI compatible endpoint use `gemini-3.8-flash`. Check Google AI Studio for the current list and for your free tier limits before you set `LLM_MODEL`.
* Free tiers may use prompts to improve the provider's products. That is acceptable here because we only send public data and our own sample code. The Responsible AI note must say this and must say that a bank would use a private deployment in its own cloud tenant.
* `LLM_MODEL_VALIDATOR` is optional. When set, the validator agent in factory_core uses a different model from the developer agents, which strengthens validation independence.
* The frontend has its own `.env` inside its folder with `VITE_API_MODE` (`mock`, `live` or `snapshot`) and `VITE_API_BASE_URL`.

## 12. LLM client rules (factory_core and redev_engine each keep their own small copy)

Both services implement the same small module `llm_client.py` inside their own folder. There is no shared code package, on purpose, so nobody edits a file that someone else owns.

* Use the official `openai` Python SDK with `base_url=LLM_BASE_URL` and `api_key=LLM_API_KEY`, chat completions API, temperature from `LLM_TEMPERATURE`.
* One function: `complete(system: str, user: str, *, json_mode: bool = False, step: str = "", model: str | None = None) -> LLMResponse` where `LLMResponse` has `text, model, input_tokens, output_tokens, latency_ms, cached, prompt_sha256`.
* Cache. The cache key is the SHA 256 of model, system and user text. Every live response is saved as a JSON file in `<service>/llm_cache/`. The cache folder is committed to the repository.
* `LLM_MODE=live`: use the cache when the key exists, otherwise call the provider and store the response. `LLM_MODE=replay`: serve only from cache and raise a clear error when a key is missing. Replay mode lets the demo and the judges run the whole pipeline with no key and no network.
* Retry with exponential backoff on rate limit and server errors, at most 4 attempts.
* When `json_mode` is true, parse and validate the reply against a Pydantic model. On invalid JSON, retry once with the validation error appended.
* Return the trace fields so that factory_core can write an `llm_call` audit event for every call.
* Never send secrets. Never send data rows beyond the small samples a prompt really needs.

## 13. Priorities and milestones

Priority levels used in every member plan:

* P0, must have: one complete, real, end to end run on the hero model through all five stages with human gates, visible in the UI.
* P1, should have: all four models in the inventory with documentation, document drift list, monitoring with revalidation trigger, SS1/23 matrix, audit timeline, DOCX report, evaluation numbers for the deck, replay cache, static snapshot for the deployed link.
* P2, nice to have: MLflow registry and Azure ML tracking, Azure deployment of the backend, batch run over the whole estate.

Milestones:

| Milestone | Meaning | Who |
|---|---|---|
| M0 | Skeleton on `main`: root files, `contracts/examples/`, `docs/PROJECT_CONTEXT.md`. Everyone on a personal branch. | Varun |
| M1 | Every service starts alone and returns contract shaped responses (stub or real). Frontend runs fully on mocks. | All |
| M2 | Hero model in the estate: data, legacy code, old document, golden outputs. | Dhrishit |
| M3 | First real end to end run on the hero model, UI in live mode. | All |
| M4 | All four models through their stages. Monitoring, compliance matrix, audit timeline. | All |
| M5 | Replay cache recorded, snapshot exported, deployed link, submission pack. | All |

## 14. The three minute demo story (build for this)

1. Dashboard. Four legacy models found, all documents outdated, tiers assigned.
2. Open M001. The passport shows five stamps. Stamp 1: inventory record and tier rationale. A human approves the gate.
3. Documentation. Click a claim and the exact SAS lines appear as evidence. The drift list shows the differences against the 2021 document.
4. Redevelopment. SAS and Python side by side. The iteration history shows what failed, how the agent diagnosed it and the fix. The parity certificate shows records compared, largest difference and decision match rate.
5. Validation. Discrimination, calibration, stability and fairness by sex and age band. Findings table. Report download. The independence rule blocks the same reviewer from approving both redevelopment and validation.
6. Monitoring. Drift appears in a simulated batch, the alert turns red and revalidation is triggered.
7. Audit trail, SS1/23 matrix and factory numbers.
