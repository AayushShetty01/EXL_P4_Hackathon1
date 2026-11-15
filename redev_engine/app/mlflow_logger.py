"""Optional MLflow tracking: logs parity metrics and artifacts and registers the rebuilt model when MLFLOW_TRACKING_URI is set."""

from pathlib import Path

from app.config import get_settings
from app.schemas import RedevelopResult


def log_run(result: RedevelopResult, out_dir: Path) -> dict | None:
    """Log one redevelopment run; return {'run_id', 'registered_model'} or None when MLflow is not configured."""
    uri = get_settings().mlflow_tracking_uri
    if not uri:
        return None
    try:
        import mlflow
        import mlflow.pyfunc
    except ImportError:
        return {"error": "MLFLOW_TRACKING_URI is set but the mlflow package is not installed"}
    try:
        mlflow.set_tracking_uri(uri)
        mlflow.set_experiment("redev_engine")
        with mlflow.start_run(run_name=f"{result.model_id}_{result.run_id}") as run:
            mlflow.log_params({"model_id": result.model_id, "source_language": result.source_language,
                               "status": result.status, "iterations": len(result.iterations)})
            if result.parity:
                mlflow.log_metric("records_compared", result.parity.records_compared)
                for level in result.parity.levels:
                    for field in ("max_abs_diff", "match_rate", "psi"):
                        value = getattr(level, field)
                        if value is not None:
                            mlflow.log_metric(f"{level.level}_{field}", value)
            mlflow.log_artifacts(str(out_dir), artifact_path="redevelop")
            registered = None
            if result.status == "PARITY_PASSED":
                registered = register_model(mlflow, out_dir / "model.py", result.model_id)
            return {"run_id": run.info.run_id, "registered_model": registered}
    except Exception as error:  # noqa: BLE001 - tracking must never break the rebuild
        return {"error": f"MLflow logging failed: {error}"}


def register_model(mlflow, model_path: Path, model_id: str) -> str:
    """Register model.py as an MLflow pyfunc model named after the model id."""

    class RebuiltModel(mlflow.pyfunc.PythonModel):
        """pyfunc wrapper that calls score() of the rebuilt model."""

        def load_context(self, context):
            """Import model.py from the logged artifacts."""
            import importlib.util

            spec = importlib.util.spec_from_file_location("model", context.artifacts["model_code"])
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

        def predict(self, context, model_input):
            """Score a DataFrame with the deployed coefficients."""
            return self.module.score(model_input)

    mlflow.pyfunc.log_model(artifact_path="model", python_model=RebuiltModel(),
                            artifacts={"model_code": str(model_path)}, registered_model_name=model_id)
    return model_id
