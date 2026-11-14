"""Contract shapes of validation_lab validation and report calls, section 9.2 of docs/PROJECT_CONTEXT.md.

The monitoring calls of validation_lab are in monitoring_schemas.py.
"""

from __future__ import annotations

from typing import Any

from app.schemas import ContractModel, ModelType, Rating, ServiceModel, Severity


class ValidateData(ContractModel):
    """Data files for validation, relative to the repository root."""

    dev_path: str
    oot_path: str
    id_col: str
    target_col: str


class ValidateScores(ContractModel):
    """Scored files for validation, relative to the repository root."""

    dev_path: str
    oot_path: str
    pd_col: str
    score_col: str
    decision_col: str


class ValidateRequest(ContractModel):
    """Body of POST /validate."""

    run_id: str
    model_id: str
    model_type: ModelType
    data: ValidateData
    scores: ValidateScores
    feature_cols: list[str]
    protected_cols: list[str]
    model_module_path: str | None = None
    thresholds: dict[str, float] | None = None


class DataQualityCheck(ServiceModel):
    """One data quality check."""

    check: str
    value: float
    threshold: float
    passed: bool


class DataQuality(ServiceModel):
    """Data quality section."""

    rating: Rating
    checks: list[DataQualityCheck]
    target_rate: dict[str, float]


class DiscriminationSample(ServiceModel):
    """Discrimination metrics on one sample."""

    auc: float
    gini: float
    ks: float


class Discrimination(ServiceModel):
    """Discrimination section."""

    rating: Rating
    dev: DiscriminationSample
    oot: DiscriminationSample
    gini_relative_drop: float


class CalibrationHoldout(ServiceModel):
    """Calibration metrics on the holdout sample."""

    brier: float
    mean_predicted_pd: float
    observed_default_rate: float
    observed_over_expected: float
    hosmer_lemeshow_stat: float
    hosmer_lemeshow_p: float


class DecileRow(ServiceModel):
    """One row of the calibration decile table."""

    decile: int
    n: int
    mean_pd: float
    observed_rate: float


class Calibration(ServiceModel):
    """Calibration section."""

    rating: Rating
    oot: CalibrationHoldout
    decile_table: list[DecileRow]


class FeatureCsi(ServiceModel):
    """Characteristic stability of one feature."""

    feature: str
    csi: float
    rating: Rating


class Stability(ServiceModel):
    """Stability section."""

    rating: Rating
    psi_score: float
    csi: list[FeatureCsi]


class BacktestBand(ServiceModel):
    """One PD band of the back test."""

    band: str
    pd_min: float
    pd_max: float
    n: int
    mean_pd: float
    observed_rate: float
    binomial_p: float
    light: Rating


class Backtest(ServiceModel):
    """Back test section."""

    rating: Rating
    bands: list[BacktestBand]


class FairnessGroup(ServiceModel):
    """Outcome rates of one group of a protected attribute."""

    group: str
    n: int
    approval_rate: float
    approval_rate_good_customers: float
    approval_rate_bad_customers: float
    observed_default_rate: float
    mean_pd: float


class FairnessAttribute(ServiceModel):
    """Fairness results for one protected attribute."""

    attribute: str
    groups: list[FairnessGroup]
    demographic_parity_ratio: float
    equal_opportunity_diff: float
    equalized_odds_diff: float
    rating: Rating


class Fairness(ServiceModel):
    """Fairness section."""

    rating: Rating
    favourable_outcome: str
    by_attribute: list[FairnessAttribute]


class SensitivityShock(ServiceModel):
    """Effect of one input shock."""

    feature: str
    shock: str
    mean_pd_change: float
    decision_flip_rate: float


class Sensitivity(ServiceModel):
    """Sensitivity section."""

    rating: Rating
    shocks: list[SensitivityShock]


class Benchmark(ServiceModel):
    """Challenger model comparison."""

    rating: Rating
    challenger: str
    champion_auc_oot: float
    challenger_auc_oot: float
    auc_uplift: float


class ValidationSections(ServiceModel):
    """All validation sections. Sensitivity and benchmark may be null."""

    data_quality: DataQuality
    discrimination: Discrimination
    calibration: Calibration
    stability: Stability
    backtest: Backtest
    fairness: Fairness
    sensitivity: Sensitivity | None = None
    benchmark: Benchmark | None = None


class FindingEvidence(ServiceModel):
    """The metric behind a finding."""

    metric: str
    value: float | str | None = None
    threshold: float | str | None = None


class Finding(ServiceModel):
    """One rated validation finding."""

    id: str
    section: str
    severity: Severity
    title: str
    detail: str
    evidence: FindingEvidence | None = None
    recommendation: str | None = None


class Chart(ServiceModel):
    """A chart image written by validation_lab."""

    id: str
    title: str
    path: str


class ValidationResult(ServiceModel):
    """Response of POST /validate."""

    model_id: str
    run_id: str
    status: str
    overall_rating: Rating | None = None
    sample_sizes: dict[str, int]
    sections: ValidationSections | None = None
    findings: list[Finding] = []
    charts: list[Chart] = []
    series: dict[str, list[dict[str, Any]]] = {}
    thresholds_used: dict[str, float] = {}
    result_path: str | None = None
    duration_seconds: float | None = None
    error: str | None = None


class ReportResponse(ServiceModel):
    """Response of POST /report."""

    model_id: str
    html_path: str | None = None
    docx_path: str | None = None
    error: str | None = None
