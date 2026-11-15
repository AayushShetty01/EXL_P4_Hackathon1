# score.py
# Card fraud detector - score transactions and write decisions
# 2022

from pathlib import Path

import pandas as pd

from train import DATA_DIR, build_matrix, train_model

OUT_DIR = Path(__file__).resolve().parents[1] / "golden"
THRESHOLD = 0.06


def score_file(model, name):
    df = pd.read_csv(DATA_DIR / (name + ".csv"))
    p = model.predict_proba(build_matrix(df))[:, 1]
    out = pd.DataFrame({"ID": df["ID"], "pd": p, "score": 0})
    out["decision"] = ["DECLINE" if x > THRESHOLD else "APPROVE" for x in p]
    out.to_csv(OUT_DIR / ("scored_" + name + "_legacy.csv"), index=False, float_format="%.17g")
    return out


if __name__ == "__main__":
    model = train_model()
    OUT_DIR.mkdir(exist_ok=True)
    for name in ["dev", "oot"]:
        res = score_file(model, name)
        print(name, len(res), "declined", (res["decision"] == "DECLINE").sum())
