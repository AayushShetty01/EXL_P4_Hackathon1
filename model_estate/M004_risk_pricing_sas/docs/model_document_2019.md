# Personal Loan Risk Based Pricing Model

Model documentation, version 2.0

| Item | Value |
|---|---|
| Model owner | Head of Lending Pricing |
| Developer | Pricing Analytics |
| Business line | Pricing |
| Document date | 4 November 2019 |
| Model status | In production |

## 1. Purpose

The model sets the interest rate offered on a personal loan from the applicant's probability of default at origination and the expected margin of the loan. It is used for pricing only. Credit approval is decided by the application scorecard.

## 2. Components

The model has two parts:

1. A rule based pricing tier assigned from the probability of default at origination.
2. A linear regression that predicts the realised margin of a loan, fitted on the loan book.

## 3. Pricing tiers

| Tier | Probability of default at origination | Rate add on |
|---|---|---|
| A | below 2 percent | 1.0 percent |
| B | 2 to 5 percent | 2.5 percent |
| C | 5 to 10 percent | 4.5 percent |
| D | 10 to 25 percent | 7.5 percent |
| X | 25 percent and above | Declined |

## 4. Margin regression

The realised margin is interest income less funding cost, credit loss and servicing cost, divided by the average balance. It is modelled with ordinary least squares in SAS PROC REG on loans with at least 12 months on book from the 2016 to 2019 book. The predictors are:

* Probability of default at origination
* Log of the loan amount
* Term in months
* Loan to value ratio

## 5. Offer rate

The offer rate is the base rate of 3.75 percent plus the tier add on, plus any shortfall of the expected margin below 2 percent. The rate is rounded to the nearest 0.05 percent and capped at 19.9 percent.

## 6. Limitations

* The margin regression assumes a linear relationship and has not been tested for interactions.
* Funding cost is taken as a fixed internal transfer price.

## 7. Monitoring

The pricing committee reviews offer rates and realised margins every quarter.
