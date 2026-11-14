"""Contract shapes of validation_lab monitoring calls, section 9.2 of docs/PROJECT_CONTEXT.md."""

from __future__ import annotations

from app.schemas import ContractModel, Rating, ServiceModel


class MonitorSimulateRequest(ContractModel):
    """Body of POST /monitor/simulate."""

    model_id: str
    data_path: str
    scores_path: str
    id_col: str
    target_col: str
    pd_col: str
    score_col: str
    feature_cols: list[str]
    n_batches: int
    batch_size: int
    drift_start_batch: int
    drift_strength: float
    seed: int


class SimulatedBatch(ServiceModel):
    """One simulated production batch file."""

    batch: str
    path: str
    n: int
    drift_injected: bool


class MonitorSimulateResponse(ServiceModel):
    """Response of POST /monitor/simulate."""

    model_id: str
    simulated: bool
    batches_dir: str
    batches: list[SimulatedBatch]
    error: str | None = None


class MonitorReference(ContractModel):
    """Reference sample for monitoring."""

    data_path: str
    scores_path: str


class MonitorRunRequest(ContractModel):
    """Body of POST /monitor/run."""

    model_id: str
    reference: MonitorReference
    batches_dir: str
    id_col: str
    target_col: str
    pd_col: str
    score_col: str
    feature_cols: list[str]
    thresholds: dict[str, float] | None = None


class MaxCsi(ServiceModel):
    """The least stable feature of a batch."""

    feature: str
    csi: float


class MonitoringBatch(ServiceModel):
    """Drift and performance of one batch."""

    batch: str
    n: int
    psi_score: float
    max_csi: MaxCsi | None = None
    auc: float | None = None
    observed_default_rate: float | None = None
    mean_pd: float | None = None
    alert: Rating


class MonitoringAlert(ServiceModel):
    """An alert raised by a monitoring rule."""

    batch: str
    level: Rating
    rule: str
    value: float


class MonitoringResult(ServiceModel):
    """Response of POST /monitor/run, also served by GET /api/models/{model_id}/monitoring."""

    model_id: str
    status: str
    simulated: bool
    reference_sample: str
    batches: list[MonitoringBatch]
    alerts: list[MonitoringAlert] = []
    revalidation_triggered: bool
    trigger_reason: str | None = None
    thresholds_used: dict[str, float] = {}
    result_path: str | None = None
    error: str | None = None
