"""Download and prepare the development and holdout data for models M001, M002 and M003.

Run from the repository root: python model_estate/_tools/prepare_data.py
Same inputs always give byte identical output files (fixed seed 42).
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
ESTATE_DIR = Path(__file__).resolve().parents[1]
M001_DIR = ESTATE_DIR / "M001_cc_pd_scorecard_sas" / "data"
M002_DIR = ESTATE_DIR / "M002_loan_pd_glm_r" / "data"
M003_DIR = ESTATE_DIR / "M003_txn_fraud_gbm_py" / "data"

M001_COLUMNS = (
    ["LIMIT_BAL", "SEX", "EDUCATION", "MARRIAGE", "AGE"]
    + ["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]
    + [f"BILL_AMT{i}" for i in range(1, 7)]
    + [f"PAY_AMT{i}" for i in range(1, 7)]
)
M001_PAY_STATUS_TEXT = "-1 pay duly, 1 to 9 months of payment delay; -2 and 0 also occur in the data"
M001_DESCRIPTIONS = {
    "ID": ("Customer record identifier, source row order", "id"),
    "LIMIT_BAL": ("Amount of given credit in NT dollars, individual plus family", "input"),
    "SEX": ("Gender code (1 male, 2 female). Protected attribute, never a model input", "protected"),
    "EDUCATION": ("Education code (1 graduate school, 2 university, 3 high school, 4 others, 0/5/6 unknown)", "unused"),
    "MARRIAGE": ("Marital status code (1 married, 2 single, 3 others, 0 unknown)", "unused"),
    "AGE": ("Age in years", "unused"),
    "PAY_0": (f"Repayment status in September 2005 ({M001_PAY_STATUS_TEXT})", "input"),
    "PAY_2": (f"Repayment status in August 2005 ({M001_PAY_STATUS_TEXT})", "input"),
    "PAY_3": (f"Repayment status in July 2005 ({M001_PAY_STATUS_TEXT})", "input"),
    "PAY_4": (f"Repayment status in June 2005 ({M001_PAY_STATUS_TEXT})", "input"),
    "PAY_5": (f"Repayment status in May 2005 ({M001_PAY_STATUS_TEXT})", "input"),
    "PAY_6": (f"Repayment status in April 2005 ({M001_PAY_STATUS_TEXT})", "input"),
    "BILL_AMT1": ("Bill statement amount in September 2005, NT dollars", "input"),
    "BILL_AMT2": ("Bill statement amount in August 2005, NT dollars", "input"),
    "BILL_AMT3": ("Bill statement amount in July 2005, NT dollars", "unused"),
    "BILL_AMT4": ("Bill statement amount in June 2005, NT dollars", "unused"),
    "BILL_AMT5": ("Bill statement amount in May 2005, NT dollars", "unused"),
    "BILL_AMT6": ("Bill statement amount in April 2005, NT dollars", "input"),
    "PAY_AMT1": ("Amount paid in September 2005, NT dollars", "input"),
    "PAY_AMT2": ("Amount paid in August 2005, NT dollars", "input"),
    "PAY_AMT3": ("Amount paid in July 2005, NT dollars", "input"),
    "PAY_AMT4": ("Amount paid in June 2005, NT dollars", "input"),
    "PAY_AMT5": ("Amount paid in May 2005, NT dollars", "input"),
    "PAY_AMT6": ("Amount paid in April 2005, NT dollars", "input"),
    "default_flag": ("1 when the customer defaulted on the payment next month, else 0", "target"),
    "AGE_BAND": ("Age band derived from AGE: 18_29, 30_39, 40_49, 50_plus. Protected attribute", "protected"),
}

M002_COLUMNS = {
    "Attribute1": ("checking_account_status", "Status of existing checking account (A11 below 0 DM, A12 0 to 199 DM, A13 200 DM or more, A14 no account)", "input"),
    "Attribute2": ("duration_months", "Loan duration in months", "input"),
    "Attribute3": ("credit_history", "Credit history code (A30 to A34)", "input"),
    "Attribute4": ("purpose", "Loan purpose code (A40 to A410)", "unused"),
    "Attribute5": ("credit_amount", "Credit amount in Deutsche Mark", "input"),
    "Attribute6": ("savings_account", "Savings account or bonds code (A61 to A65)", "input"),
    "Attribute7": ("employment_since", "Present employment since code (A71 to A75)", "unused"),
    "Attribute8": ("installment_rate_pct", "Instalment rate in percentage of disposable income", "input"),
    "Attribute9": ("personal_status_sex", "Personal status and sex code (A91 to A95). Protected attribute, never a model input", "protected"),
    "Attribute10": ("other_debtors", "Other debtors or guarantors code (A101 to A103)", "unused"),
    "Attribute11": ("residence_since", "Present residence since, years", "unused"),
    "Attribute12": ("property", "Property code (A121 to A124)", "unused"),
    "Attribute13": ("age", "Age in years. Protected attribute, never a model input", "protected"),
    "Attribute14": ("other_installment_plans", "Other instalment plans code (A141 to A143)", "input"),
    "Attribute15": ("housing", "Housing code (A151 rent, A152 own, A153 for free)", "input"),
    "Attribute16": ("existing_credits", "Number of existing credits at this bank", "unused"),
    "Attribute17": ("job", "Job code (A171 to A174)", "unused"),
    "Attribute18": ("people_liable", "Number of people liable to provide maintenance for", "unused"),
    "Attribute19": ("telephone", "Telephone code (A191 none, A192 yes)", "unused"),
    "Attribute20": ("foreign_worker", "Foreign worker code (A201 yes, A202 no)", "unused"),
}
M002_SOURCE_DESCRIPTIONS = [
    "Status of existing checking account", "Duration", "Credit history", "Purpose", "Credit amount",
    "Savings account/bonds", "Present employment since", "Installment rate in percentage of disposable income",
    "Personal status and sex", "Other debtors / guarantors", "Present residence since", "Property", "Age",
    "Other installment plans", "Housing", "Number of existing credits at this bank", "Job",
    "Number of people being liable to provide maintenance for", "Telephone", "foreign worker",
]

M003_DESCRIPTIONS = {
    "ID": ("Transaction identifier", "id"),
    "amount": ("Transaction amount in GBP", "input"),
    "hour": ("Hour of the day the transaction was made, 0 to 23", "input"),
    "merchant_category": ("Merchant category", "input"),
    "distance_from_home_km": ("Distance between merchant and cardholder home address, km", "input"),
    "txn_count_24h": ("Number of transactions on the card in the previous 24 hours", "input"),
    "card_present": ("1 when the card was physically present, 0 for card not present", "input"),
    "AGE_BAND": ("Cardholder age band: 18_29, 30_39, 40_49, 50_plus. Protected attribute, never a model input", "protected"),
    "fraud_flag": ("1 when the transaction was confirmed as fraud, else 0", "target"),
}


def age_band(age: pd.Series) -> pd.Series:
    """Map age in years to the bands 18_29, 30_39, 40_49, 50_plus."""
    return pd.cut(age, bins=[0, 29, 39, 49, 200], labels=["18_29", "30_39", "40_49", "50_plus"]).astype(str)


def stratified_split(df: pd.DataFrame, target: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split 70/30 stratified on the target with seed 42, both parts sorted by ID."""
    dev = df.groupby(target, group_keys=False).sample(frac=0.7, random_state=SEED)
    oot = df.drop(dev.index)
    return dev.sort_values("ID"), oot.sort_values("ID")


def write_model_data(folder: Path, df: pd.DataFrame, target: str, descriptions: dict) -> None:
    """Write dev.csv, oot.csv and data_dictionary.csv for one model and print a summary."""
    folder.mkdir(parents=True, exist_ok=True)
    dev, oot = stratified_split(df, target)
    dev.to_csv(folder / "dev.csv", index=False)
    oot.to_csv(folder / "oot.csv", index=False)
    dictionary = pd.DataFrame(
        [(col, *descriptions[col]) for col in df.columns], columns=["column", "description", "role"]
    )
    dictionary.to_csv(folder / "data_dictionary.csv", index=False)
    print(
        f"{folder.relative_to(ESTATE_DIR.parent)}: dev {len(dev)} rows (target rate {dev[target].mean():.4f}), "
        f"oot {len(oot)} rows (target rate {oot[target].mean():.4f})"
    )


def load_m001(manual_file: str | None) -> pd.DataFrame:
    """Load UCI dataset 350 and map it to the standard column names, checking the mapping."""
    if manual_file:
        path = Path(manual_file)
        raw = pd.read_excel(path, header=1) if path.suffix in {".xls", ".xlsx"} else pd.read_csv(path)
        expected = ["ID", *M001_COLUMNS, "default payment next month"]
        if list(raw.columns) != expected:
            raise ValueError(f"Unexpected columns in {path}: {list(raw.columns)}")
        df = raw.rename(columns={"default payment next month": "default_flag"})
    else:
        from ucimlrepo import fetch_ucirepo

        repo = fetch_ucirepo(id=350)
        described = repo.variables.set_index("name")["description"]
        mapping = {f"X{i}": name for i, name in enumerate(M001_COLUMNS, start=1)}
        for source, name in mapping.items():
            if described[source] != name:
                raise ValueError(f"UCI variable {source} is described as {described[source]!r}, expected {name!r}")
        if described["Y"] != "default payment next month":
            raise ValueError(f"UCI target is described as {described['Y']!r}")
        df = pd.concat([repo.data.ids, repo.data.features.rename(columns=mapping), repo.data.targets], axis=1)
        df = df.rename(columns={"Y": "default_flag"})
    if len(df) != 30000 or df["ID"].duplicated().any():
        raise ValueError(f"Expected 30000 unique rows for M001, got {len(df)}")
    df["AGE_BAND"] = age_band(df["AGE"])
    return df[["ID", *M001_COLUMNS, "default_flag", "AGE_BAND"]]


def load_m002(manual_file: str | None) -> pd.DataFrame:
    """Load UCI dataset 144, give the columns readable names and add the target and AGE_BAND."""
    if manual_file:
        raw = pd.read_csv(manual_file, sep=r"\s+", header=None, names=[*M002_COLUMNS, "class"])
    else:
        from ucimlrepo import fetch_ucirepo

        repo = fetch_ucirepo(id=144)
        described = repo.variables.set_index("name")["description"]
        for source, text in zip(M002_COLUMNS, M002_SOURCE_DESCRIPTIONS):
            if described[source] != text:
                raise ValueError(f"UCI variable {source} is described as {described[source]!r}, expected {text!r}")
        raw = pd.concat([repo.data.features, repo.data.targets], axis=1)
    if len(raw) != 1000 or set(raw["class"]) != {1, 2}:
        raise ValueError("Expected 1000 rows with class 1 (good) or 2 (bad) for M002")
    df = raw.rename(columns={source: name for source, (name, _, _) in M002_COLUMNS.items()})
    df.insert(0, "ID", range(1, len(df) + 1))
    df["default_flag"] = (df.pop("class") == 2).astype(int)
    df["AGE_BAND"] = age_band(df["age"])
    return df


def generate_m003(n_rows: int = 20000, fraud_rate: float = 0.015) -> pd.DataFrame:
    """Generate synthetic card transactions with a fixed seed and a known fraud mechanism."""
    rng = np.random.default_rng(SEED)
    categories = ["grocery", "fuel", "restaurant", "online_retail", "travel", "electronics", "cash_withdrawal"]
    category_share = [0.30, 0.12, 0.16, 0.22, 0.06, 0.08, 0.06]
    category_risk = dict(zip(categories, [-0.6, -0.4, -0.5, 0.6, 0.5, 0.9, 0.7]))

    age_bands = rng.choice(["18_29", "30_39", "40_49", "50_plus"], size=n_rows, p=[0.22, 0.27, 0.24, 0.27])
    category = rng.choice(categories, size=n_rows, p=category_share)
    amount = np.round(rng.lognormal(mean=3.4, sigma=1.0, size=n_rows), 2)
    hour = rng.choice(24, size=n_rows, p=np.r_[[0.01] * 6, [0.045] * 18] / np.r_[[0.01] * 6, [0.045] * 18].sum())
    distance = np.round(rng.gamma(shape=1.2, scale=12.0, size=n_rows), 1)
    txn_count = rng.poisson(lam=2.0, size=n_rows)
    online = np.isin(category, ["online_retail"])
    card_present = np.where(online, 0, rng.binomial(1, 0.85, size=n_rows))

    risk = (
        0.55 * np.log1p(amount)
        + 0.9 * ((hour <= 5).astype(float))
        + 0.025 * distance
        + 0.30 * txn_count
        + -0.9 * card_present
        + np.vectorize(category_risk.get)(category)
    )
    low, high = -30.0, 10.0
    for _ in range(100):
        intercept = (low + high) / 2
        mean_rate = (1 / (1 + np.exp(-(intercept + risk)))).mean()
        low, high = (intercept, high) if mean_rate < fraud_rate else (low, intercept)
    fraud = rng.binomial(1, 1 / (1 + np.exp(-(intercept + risk))))

    return pd.DataFrame(
        {
            "ID": np.arange(1, n_rows + 1),
            "amount": amount,
            "hour": hour,
            "merchant_category": category,
            "distance_from_home_km": distance,
            "txn_count_24h": txn_count,
            "card_present": card_present,
            "AGE_BAND": age_bands,
            "fraud_flag": fraud,
        }
    )


def main() -> None:
    """Parse the command line and write the data files for M001, M002 and M003."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--m001-file", help="manually downloaded 'default of credit card clients.xls' (or .csv)")
    parser.add_argument("--m002-file", help="manually downloaded 'german.data'")
    args = parser.parse_args()

    write_model_data(M001_DIR, load_m001(args.m001_file), "default_flag", M001_DESCRIPTIONS)
    m002_descriptions = {name: (text, role) for name, text, role in M002_COLUMNS.values()}
    m002_descriptions |= {
        "ID": ("Application identifier, source row order", "id"),
        "default_flag": ("1 when the applicant was rated a bad credit risk, else 0", "target"),
        "AGE_BAND": ("Age band derived from age: 18_29, 30_39, 40_49, 50_plus. Protected attribute", "protected"),
    }
    write_model_data(M002_DIR, load_m002(args.m002_file), "default_flag", m002_descriptions)
    write_model_data(M003_DIR, generate_m003(), "fraud_flag", M003_DESCRIPTIONS)


if __name__ == "__main__":
    main()
