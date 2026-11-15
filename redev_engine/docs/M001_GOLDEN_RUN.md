# How to produce the M001 golden files

The golden files are the outputs of the legacy SAS programs. They must come from a real SAS run. Never create or edit them by hand.

Environment: SAS OnDemand for Academics (SAS Studio in the browser, SAS 9.4 with Base SAS and SAS/STAT).

## Steps

1. Sign in to SAS OnDemand for Academics and open SAS Studio.
2. In the Server Files and Folders pane, create the folder `M001` under your home folder (Files (Home) > New folder).
3. Upload `model_estate/M001_cc_pd_scorecard_sas/data/dev.csv` and `data/oot.csv` into `M001`.
4. Right click the `M001` folder > Properties and copy its location, for example `/home/u12345678/M001`.
5. Open `code/01_prepare.sas`, `code/02_train.sas` and `code/03_score.sas` in SAS Studio (upload them or paste their content). In each one replace the line `%let path=/home/your_user_id/M001;` with your folder location. Change nothing else.
6. Run the three programs in order: 01, 02, 03. After each run open the Log tab and check that there are no lines starting with `ERROR`. Notes about division by zero and missing values are expected.
7. Create the folder `model_estate/M001_cc_pd_scorecard_sas/golden/` and download these three files from the `M001` folder into it:
   * `coefficients_legacy.csv` (columns `variable, estimate`)
   * `scored_dev_legacy.csv` (columns `ID, pd, score, decision`, 21,000 rows)
   * `scored_oot_legacy.csv` (columns `ID, pd, score, decision`, 9,000 rows)
8. Save the logs of the three runs, one after the other, as `golden/run_log.txt` (Log tab > Save or copy and paste).
9. In `manifest.json` replace `"golden": null` with:

```json
"golden": {
  "scored_dev_path": "golden/scored_dev_legacy.csv",
  "scored_oot_path": "golden/scored_oot_legacy.csv",
  "coefficients_path": "golden/coefficients_legacy.csv",
  "produced_by": "SAS OnDemand for Academics",
  "produced_on": "YYYY-MM-DD"
}
```

## Checks before committing

* `pd` values show many decimals (for example `0.123456789012345`). If they show only a few, the `best32.` format was not applied and parity will show false differences.
* `coefficients_legacy.csv` has 9 rows: `Intercept` and the eight `woe_` variables.
* If SAS reports an error, keep the log and fix the program before trying again. Only the files from a clean run go into this folder.
