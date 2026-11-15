# train.py
# Card fraud detector - train gradient boosting model on dev transactions
# 2022

from pathlib import Path

import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
FEATURES = ["amount", "hour", "distance_from_home_km", "txn_count_24h", "card_present"]
CATEGORIES = ["grocery", "fuel", "restaurant", "online_retail", "travel", "electronics", "cash_withdrawal"]


def build_matrix(df):
    X = df[FEATURES].copy()
    for cat in CATEGORIES:
        X["mcc_" + cat] = (df["merchant_category"] == cat).astype(int)
    X["night"] = (df["hour"] < 6).astype(int)
    return X


def train_model():
    dev = pd.read_csv(DATA_DIR / "dev.csv")
    model = GradientBoostingClassifier(
        n_estimators=150, learning_rate=0.05, max_depth=3, subsample=0.8, random_state=7
    )
    model.fit(build_matrix(dev), dev["fraud_flag"])
    return model


if __name__ == "__main__":
    m = train_model()
    print("trained", m.n_estimators_, "trees")
