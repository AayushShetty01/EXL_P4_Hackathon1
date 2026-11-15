# Model estate

The estate lives in `model_estate/` at the repository root, because every service reads it by that path.

The sample bank: four legacy models in SAS, R and Python with their code, outdated model documents, data and legacy (golden) outputs. Every service in ModelPassport reads this folder. Only the estate owner changes it.

## Models

| Model id | Folder | Model | Language | Golden outputs |
|---|---|---|---|---|
| M001 | `M001_cc_pd_scorecard_sas/` | Credit card probability of default scorecard (WoE logistic regression) | SAS | From a SAS OnDemand run, see `M001_GOLDEN_RUN.md` |
| M002 | `M002_loan_pd_glm_r/` | Personal loan probability of default (binomial GLM) | R | From `Rscript`, log in `golden/run_log.txt` |
| M003 | `M003_txn_fraud_gbm_py/` | Card transaction fraud detector (gradient boosting) | Python | From `code/score.py` |
| M004 | `M004_risk_pricing_sas/` | Risk based loan pricing (rules plus linear regression) | SAS | None. Documented only, never executed |

## Folder map (paths inside `model_estate/`)

| Path | Contents |
|---|---|
| `estate_register.csv` | The bank's stale inventory spreadsheet |
| `M00X_*/manifest.json` | Technical pointers: code files, document files, data and golden paths |
| `M00X_*/code/` | Legacy source code |
| `M00X_*/docs/` | The old model document, which no longer matches the code |
| `M00X_*/data/` | `dev.csv`, `oot.csv` (70/30 stratified split) and `data_dictionary.csv` |
| `M00X_*/golden/` | Legacy outputs: `scored_dev_legacy.csv`, `scored_oot_legacy.csv`, `coefficients_legacy.csv`, run log |
| `_tools/prepare_data.py` | Downloads and prepares the data for M001, M002 and M003 |
| `_tools/derive_woe_m001.py` | Computes the WoE constants that are hard coded in the M001 SAS code |
| `_tools/make_golden_m002.R` | Runs the M002 R model and writes its golden outputs |
| `_answer_keys/` | Expected inventory fields and seeded document differences, for evaluation scripts only. Agents must never read this folder |

## How to regenerate the data

From the repository root, with Python 3.11 or newer and `pandas`, `numpy` and `ucimlrepo` installed:

```
python model_estate/_tools/prepare_data.py
```

Without internet access, download the files from the UCI repository and pass them in:

```
python model_estate/_tools/prepare_data.py --m001-file "default of credit card clients.xls" --m002-file german.data
```

Reading the `.xls` file needs the `xlrd` package. The output is identical on every run.

## How to regenerate the golden outputs

* M001: follow `redev_engine/docs/M001_GOLDEN_RUN.md` (SAS OnDemand for Academics). Until real SAS outputs exist, `golden` is `null` in the M001 manifest.
* M002: `Rscript model_estate/_tools/make_golden_m002.R`
* M003: `cd model_estate/M003_txn_fraud_gbm_py/code && python score.py` (needs `scikit-learn`)
* M004: none.

## Conventions

* Scored files have exactly the columns `ID, pd, score, decision`. `score` is 0 for the fraud model, which has no scorecard.
* The `oot` sample is a random holdout, not an out of time sample.
* Protected attributes (`SEX`, `AGE_BAND`, `personal_status_sex`, `age`) are never model inputs.
