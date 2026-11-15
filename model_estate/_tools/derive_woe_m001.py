"""Derive the weight of evidence (WoE) constants of the M001 scorecard from dev.csv.

Prints a WoE table and the SAS IF / ELSE IF blocks that hold the constants in code/01_prepare.sas.
Features follow SAS semantics: division by zero gives missing, and missing falls in the first bin.
Run from the repository root: python model_estate/_tools/derive_woe_m001.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

DEV_PATH = Path(__file__).resolve().parents[1] / "M001_cc_pd_scorecard_sas" / "data" / "dev.csv"
PAY_STATUS = ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
PAY_AMOUNTS = [f"PAY_AMT{i}" for i in range(1, 7)]

# model variable: (feature column, upper bin edges, compared with "<")
BINS = {
    "woe_util": ("util", [0.05, 0.3, 0.6, 0.9]),
    "woe_payr": ("pay_ratio", [0.04, 0.06, 0.15, 0.5, 1]),
    "woe_worst": ("worst_status", [0, 1, 2, 3]),
    "woe_arrears": ("months_arrears", [1, 2, 4]),
    "woe_trend": ("bill_trend", [-0.05, 0.01, 0.1, 0.3]),
    "woe_pay0": ("PAY_0", [0, 1, 2]),
    "woe_limit": ("LIMIT_BAL", [50000, 100000, 200000, 350000]),
    "woe_payavg": ("pay_avg", [1000, 2500, 5000, 10000]),
}


def derive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the derived features exactly as the SAS DATA step does."""
    out = df.copy()
    out["util"] = df["BILL_AMT1"] / df["LIMIT_BAL"]
    out["pay_ratio"] = df["PAY_AMT1"] / df["BILL_AMT2"].replace(0, np.nan)
    out["worst_status"] = df[PAY_STATUS].max(axis=1)
    out["months_arrears"] = (df[PAY_STATUS] > 0).sum(axis=1)
    out["bill_trend"] = (df["BILL_AMT1"] - df["BILL_AMT6"]) / df["LIMIT_BAL"]
    out["pay_avg"] = df[PAY_AMOUNTS].mean(axis=1)
    return out


def bin_index(values: pd.Series, edges: list[float]) -> np.ndarray:
    """Index of the first bin whose condition 'value < edge' holds; missing goes to bin 0."""
    filled = values.fillna(-np.inf).to_numpy()
    return np.searchsorted(np.asarray(edges, dtype=float), filled, side="right")


def woe_table(features: pd.DataFrame, target: pd.Series) -> pd.DataFrame:
    """WoE per bin, defined as ln(share of goods / share of bads), rounded to 4 decimals."""
    rows = []
    goods, bads = (target == 0).sum(), (target == 1).sum()
    for variable, (column, edges) in BINS.items():
        index = bin_index(features[column], edges)
        for b in range(len(edges) + 1):
            in_bin = index == b
            good, bad = int(((target == 0) & in_bin).sum()), int(((target == 1) & in_bin).sum())
            rows.append(
                {
                    "variable": variable,
                    "bin": b,
                    "condition": f"{column} < {edges[b]}" if b < len(edges) else "else",
                    "n": int(in_bin.sum()),
                    "bad_rate": round(bad / max(good + bad, 1), 4),
                    "woe": round(float(np.log((good / goods) / (bad / bads))), 4),
                }
            )
    return pd.DataFrame(rows)


def sas_block(table: pd.DataFrame, variable: str) -> str:
    """Render the SAS IF / ELSE IF chain for one model variable."""
    column, edges = BINS[variable]
    woes = table.loc[table["variable"] == variable, "woe"].tolist()
    lines = [f"  if {column} < {edges[0]} then {variable} = {woes[0]};"]
    lines += [f"  else if {column} < {edge} then {variable} = {woe};" for edge, woe in zip(edges[1:], woes[1:-1])]
    lines.append(f"  else {variable} = {woes[-1]};")
    return "\n".join(lines)


def main() -> None:
    """Print the WoE table and the SAS blocks."""
    dev = pd.read_csv(DEV_PATH)
    table = woe_table(derive_features(dev), dev["default_flag"])
    print(table.to_string(index=False))
    print()
    for variable in BINS:
        print(sas_block(table, variable))


if __name__ == "__main__":
    main()
