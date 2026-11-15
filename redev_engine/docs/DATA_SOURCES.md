# Data sources

Source, licence and citation of every dataset in the model estate. All data is public or synthetic. None of it is personal data from a bank.

| Model | Dataset | Source | Licence | Rows |
|---|---|---|---|---|
| M001 | Default of Credit Card Clients | UCI Machine Learning Repository, dataset id 350 | CC BY 4.0 | 30,000 |
| M002 | Statlog (German Credit Data) | UCI Machine Learning Repository, dataset id 144 | CC BY 4.0 | 1,000 |
| M003 | Synthetic card transactions | Created by `model_estate/_tools/prepare_data.py`, seed 42 | Same licence as this repository | 20,000 |
| M004 | None | The pricing model is documented only and never executed | Not applicable | 0 |

## Citations

* M001: Yeh, I. (2009). Default of Credit Card Clients [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C55S3H
  Original study: Yeh, I. C. and Lien, C. H. (2009). The comparisons of data mining techniques for the predictive accuracy of probability of default of credit card clients. Expert Systems with Applications, 36(2), 2473 to 2480.
* M002: Hofmann, H. (1994). Statlog (German Credit Data) [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5NC77

## How the data is prepared

* M001: the UCI columns X1 to X23 are renamed to `LIMIT_BAL, SEX, EDUCATION, MARRIAGE, AGE, PAY_0, PAY_2 ... PAY_6, BILL_AMT1 ... BILL_AMT6, PAY_AMT1 ... PAY_AMT6`. The script checks every name against the variable description published with the dataset. The target `default payment next month` becomes `default_flag`. `AGE_BAND` is added.
* M002: the columns `Attribute1` to `Attribute20` get readable names (checked against the published descriptions). The category codes such as `A11` are kept as published. `default_flag` is 1 for class 2 (bad credit). `ID` is the source row order. `AGE_BAND` is added.
* M003: transactions are drawn from fixed distributions. Fraud is drawn from a logistic function of amount, night time hour, distance from home, recent transaction count, card present flag and merchant category, with the intercept set so that the fraud rate is about 1.5 percent. `AGE_BAND` does not enter the fraud function.
* Every model is split 70/30 into `dev.csv` and `oot.csv`, stratified on the target with seed 42.

## Limitations

* The `oot` file is a random holdout, not an out of time sample, because these public datasets have no usable time dimension. It is named `oot` only for pipeline consistency.
* M001 describes a Taiwanese credit card portfolio from 2005, not a UK retail book. Amounts are in NT dollars.
* M002 is a small German sample from the 1990s with amounts in Deutsche Mark.
* M003 is fully synthetic, so its accuracy says nothing about real fraud detection.
* Protected attributes (`SEX`, `AGE_BAND`, `personal_status_sex`, `age`) are kept only for fairness testing and are never model inputs.
