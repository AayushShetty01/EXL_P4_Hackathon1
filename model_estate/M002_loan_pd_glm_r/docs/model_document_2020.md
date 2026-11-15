# Personal Loan Application PD Model

Model documentation, version 1.2

| Item | Value |
|---|---|
| Model owner | Head of Personal Loans Credit Risk |
| Developer | Retail Credit Analytics |
| Business line | Personal Loans |
| Document date | 15 September 2020 |
| Model status | In production |

## 1. Purpose

The model estimates the probability that a personal loan applicant becomes a bad credit risk. It supports the approve or decline decision at application. Final decisions also apply policy rules that are outside the model.

## 2. Data

The model was developed on 700 historical applications with a known good or bad outcome. A further 300 applications, drawn at random, were held out for testing. About 30 percent of applications are bad. Amounts are in Deutsche Mark.

Age and the personal status and sex attribute are present in the data but are not used in the model.

## 3. Input variables

| Variable | Treatment |
|---|---|
| Status of checking account | Categorical, four levels |
| Credit history | Categorical, five levels |
| Savings account or bonds | Categorical, five levels |
| Loan purpose | Categorical, ten levels |
| Loan duration in months | Continuous, used as a number of months |
| Credit amount | Natural logarithm of the amount |
| Instalment rate as percentage of income | Continuous |
| Housing | Categorical, three levels, owner is the reference |
| Other instalment plans | Categorical, three levels |

## 4. Methodology

A binomial generalised linear model with the logit link is fitted in R with the `glm` function. Categorical variables use treatment contrasts. The model predicts the probability of a bad outcome.

## 5. Score and decision

The probability is converted into a score with 450 points at even odds and 40 points per unit of log odds, rounded to a whole number. A higher score means a lower risk. Applications with a score below 450 are declined.

## 6. Limitations

* The development sample is small, so some categories have few observations.
* The test sample is a random holdout, not an out of time sample.

## 7. Monitoring

Approval rate and bad rate are reviewed every six months by Retail Credit Analytics.
