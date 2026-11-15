# Card Transaction Fraud Detector

Model documentation, version 1.0

| Item | Value |
|---|---|
| Model owner | Head of Fraud Operations |
| Developer | Fraud Analytics |
| Business line | Fraud Operations |
| Document date | 10 May 2022 |
| Model status | In production |

## 1. Purpose

The model scores each card transaction in real time with the probability that it is fraudulent. Transactions above the threshold are declined and referred to the fraud team. All other transactions are allowed.

## 2. Data

Development used 14,000 labelled card transactions, with 6,000 further transactions held out for testing. About 1.5 percent of transactions are confirmed fraud.

## 3. Input features

* Transaction amount
* Hour of the day
* Merchant category
* Distance between merchant and home address
* Number of transactions on the card in the previous 24 hours
* Card present flag
* Merchant country

Cardholder age band is held for fairness monitoring only and is not a model input.

## 4. Methodology

The model is a scikit-learn gradient boosting classifier with 200 trees of depth 3 and a learning rate of 0.05. Merchant category is one hot encoded.

## 5. Decision rule

A transaction is declined when the predicted fraud probability is above 0.10.

## 6. Limitations

* Fraud patterns change quickly, so the model needs frequent monitoring.
* Confirmed fraud labels arrive with a delay of up to 60 days.

## 7. Monitoring

Monthly review of the decline rate, the fraud detection rate and the false positive rate.
