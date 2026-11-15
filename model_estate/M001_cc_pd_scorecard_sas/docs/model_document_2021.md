# Credit Card Probability of Default Scorecard

Model documentation, version 2.1

| Item | Value |
|---|---|
| Model owner | Head of Cards Credit Risk |
| Developer | Cards Credit Risk Analytics |
| Business line | Cards |
| Document date | 1 March 2021 |
| Model status | In production |

## 1. Purpose and scope

The scorecard estimates the probability that an existing credit card customer defaults on the payment due next month. The estimate is used to approve or decline credit limit and card account decisions in the Cards portfolio. The model is applied to every active card account each month.

## 2. Data

The model was developed on the credit card behavioural dataset held by Cards Credit Risk Analytics. Each record is one customer with six months of repayment history, bill statements and payments, plus the default outcome in the following month.

* Development sample: 24,000 accounts.
* Holdout sample: 6,000 accounts, drawn at random from the same population.
* Observed default rate: about 22 percent in both samples.

The holdout sample is a random sample and not an out of time sample. No separate out of time sample was available at development.

Demographic fields (sex, age, marital status and education) are present in the source data. They are not used as model inputs.

## 3. Input variables

The scorecard uses ten input variables. Each variable is grouped into bins and each bin is replaced by its weight of evidence (WoE), computed on the development sample.

| No. | Variable | Definition |
|---|---|---|
| 1 | Utilisation | Latest bill amount divided by the credit limit |
| 2 | Payment ratio | Latest payment divided by the previous bill amount |
| 3 | Worst status | Worst repayment status over the last six months |
| 4 | Months in arrears | Number of the last six months with a payment delay |
| 5 | Bill trend | Change in bill amount over six months divided by the credit limit |
| 6 | Current status | Repayment status in the latest month |
| 7 | Credit limit | Credit limit granted |
| 8 | Average payment | Average payment amount over six months |
| 9 | Average utilisation | Average bill amount over six months divided by the credit limit |
| 10 | Payment volatility | Standard deviation of the six monthly payment amounts |

## 4. Treatment of missing values

Missing utilisation values are replaced by the median utilisation of the development sample before binning. Other variables have no missing values in the source data.

## 5. Methodology

The model is a logistic regression fitted with SAS PROC LOGISTIC on the WoE transformed variables. The event modelled is default (default flag equal to 1). All variables were retained after review of significance and sign. Every coefficient has the expected negative sign, so a higher WoE leads to a lower probability of default.

The probability of default is

PD = 1 / (1 + exp(-(b0 + b1 x WoE1 + ... + bk x WoEk)))

## 6. Score scaling

The probability of default is converted to scorecard points with a standard scaling:

* 600 points at good to bad odds of 50 to 1.
* 20 points to double the odds.

Points for each variable are rounded to the nearest half point and the total score is rounded to a whole number. A higher score means a lower risk.

## 7. Decision rule

Applications scoring below 500 are declined. All other applications are approved, subject to policy rules outside the model.

## 8. Performance at development

The model showed good discrimination on both the development and holdout samples, with a Gini coefficient above 50 percent. Calibration was acceptable across score bands. Detailed performance tables are held in the development pack.

## 9. Limitations

* The holdout sample is not out of time, so stability over time was not tested at development.
* The data covers one six month window. Performance in a different economic environment may differ.
* Bin edges were set by judgement and have not been reviewed since development.

## 10. Monitoring

The model is monitored quarterly with the population stability index of the score and the Gini coefficient on recent defaults. A full revalidation is due every 12 months.

## 11. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2019 | Initial development |
| 2.0 | 2020 | Rebinning of credit limit |
| 2.1 | March 2021 | Documentation refresh, no change to the model |
