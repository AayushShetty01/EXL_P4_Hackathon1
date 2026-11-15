"""Starts and resumes pipeline runs, in background threads so the API answers at once.

The dashboard polls GET /api/runs/{run_id}. Seeding scripts and tests can run inline instead.
At startup, stages that were running when the service stopped are marked FAILED, never left hanging.
"""

import logging
import sqlite3
import threading
from collections import defaultdict
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from sqlmodel import Session, col, select

from app.api_schemas import GateDecisionRequest, RunCreateRequest
from app.audit_trail import AuditRecorder
from app.database import ModelRow, RunRow, StageRunRow, utc_timestamp
from app.gate_decisions import GateError, record_decision
from app.pipeline_context import PipelineContext, fail_stage
from app.pipeline_graph import build_pipeline_graph
from app.schemas import STAGE_NAMES

logger = logging.getLogger("factory_core")
ACTIVE_RUN_STATUSES = ("RUNNING", "AWAITING_REVIEW")
NOT_REQUESTED = "Not requested in this run."
INTERRUPTED = "factory_core stopped while this stage was running. Start a new run."


class RunRequestError(GateError):
    """A run that cannot be started; carries the HTTP status and error code for the API."""


class PipelineRunner:
    """Owns the compiled graph and the threads that run it."""

    def __init__(self, context: PipelineContext, background: bool = True) -> None:
        """Open the checkpoint database and compile the graph."""
        self.context = context
        self.background = background
        context.settings.checkpoints_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(context.settings.checkpoints_path), check_same_thread=False)
        self.graph = build_pipeline_graph(context, SqliteSaver(self.connection))
        self.threads: dict[str, threading.Thread] = {}
        self.locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)

    def start_run(self, model_id: str, request: RunCreateRequest) -> str:
        """Create the run with its five stage rows and start the graph."""
        with Session(self.context.engine) as session:
            model = session.get(ModelRow, model_id)
            if model is None:
                raise RunRequestError(404, "MODEL_NOT_FOUND", f"Model {model_id} is not registered")
            if model.source == "sample":
                raise RunRequestError(
                    409,
                    "SAMPLE_MODEL",
                    "The sample model from the contract examples cannot run. Scan the estate first.",
                )
            active = session.exec(
                select(RunRow).where(RunRow.model_id == model_id, col(RunRow.status).in_(ACTIVE_RUN_STATUSES))
            ).first()
            if active:
                raise RunRequestError(409, "RUN_ACTIVE", f"Run {active.run_id} of {model_id} is still {active.status}")
            requested = [stage for stage in STAGE_NAMES if stage in request.stages]
            run_id = self.next_run_id(session, model_id)
            session.add(
                RunRow(
                    run_id=run_id,
                    model_id=model_id,
                    status="RUNNING",
                    current_stage=requested[0],
                    auto_approve=request.auto_approve,
                    started_at=utc_timestamp(),
                )
            )
            for position, stage in enumerate(STAGE_NAMES):
                skipped = stage not in requested
                session.add(
                    StageRunRow(
                        run_id=run_id,
                        stage=stage,
                        position=position,
                        status="SKIPPED" if skipped else "PENDING",
                        skip_reason=NOT_REQUESTED if skipped else None,
                    )
                )
            model.active_run_id = run_id
            session.add(model)
            session.commit()
        for stage in STAGE_NAMES:
            if stage not in requested:
                AuditRecorder(self.context.engine, model_id, run_id, stage).record(
                    "stage_skipped", detail={"reason": NOT_REQUESTED}
                )
        self.launch(run_id, {"run_id": run_id})
        return run_id

    @staticmethod
    def next_run_id(session: Session, model_id: str) -> str:
        """run_{model_id}_{number}, one higher than any earlier run of the model."""
        existing = session.exec(select(RunRow.run_id).where(RunRow.model_id == model_id)).all()
        number = len(existing) + 1
        while f"run_{model_id}_{number:03d}" in existing:
            number += 1
        return f"run_{model_id}_{number:03d}"

    def decide(self, run_id: str, stage: str, decision: GateDecisionRequest) -> None:
        """Record a gate decision and resume the run."""
        with Session(self.context.engine) as session:
            row = session.exec(
                select(StageRunRow).where(StageRunRow.run_id == run_id, StageRunRow.stage == stage)
            ).first()
            if session.get(RunRow, run_id) is None:
                raise GateError(404, "RUN_NOT_FOUND", f"Run {run_id} does not exist")
            if row is None or row.status != "AWAITING_REVIEW":
                status = row.status if row else "missing"
                raise GateError(409, "GATE_NOT_OPEN", f"The {stage} stage is not waiting for review (status {status}).")
        with self.locks[run_id]:
            record_decision(self.context.engine, run_id, stage, decision)
        self.launch(run_id, Command(resume={"stage": stage, "decision": decision.decision}))

    def launch(self, run_id: str, payload: Any) -> None:
        """Invoke the graph for a run, in a background thread or inline."""
        if not self.background:
            self.invoke(run_id, payload)
            return
        thread = threading.Thread(target=self.invoke, args=(run_id, payload), name=f"pipeline-{run_id}", daemon=True)
        self.threads[run_id] = thread
        thread.start()

    def invoke(self, run_id: str, payload: Any) -> None:
        """Run the graph until it pauses at a gate or ends; one invocation per run at a time."""
        with self.locks[run_id]:
            try:
                self.graph.invoke(payload, {"configurable": {"thread_id": run_id}})
            except Exception as error:  # the run must show the failure instead of hanging
                logger.exception("A pipeline run stopped unexpectedly; its failure is stored with the run")
                self.fail_running_stage(run_id, f"Pipeline error: {type(error).__name__}: {error}")

    def fail_running_stage(self, run_id: str, message: str) -> None:
        """Mark the stage that is running (or the run itself) FAILED."""
        with Session(self.context.engine) as session:
            run = session.get(RunRow, run_id)
            running = session.exec(
                select(StageRunRow).where(StageRunRow.run_id == run_id, StageRunRow.status == "RUNNING")
            ).first()
            if running is None:
                run.status, run.finished_at = "FAILED", utc_timestamp()
                session.add(run)
                session.commit()
                return
            stage, model_id = running.stage, run.model_id
        fail_stage(
            self.context, run_id, stage, message, 0.0, AuditRecorder(self.context.engine, model_id, run_id, stage)
        )

    def wait(self, run_id: str, timeout: float = 60.0) -> None:
        """Wait for the background thread of a run to pause or finish."""
        thread = self.threads.get(run_id)
        if thread:
            thread.join(timeout)

    def recover_interrupted_runs(self) -> list[str]:
        """At startup: fail stages left RUNNING, and resume runs that were approved but not continued."""
        with Session(self.context.engine) as session:
            stuck = {
                row.run_id for row in session.exec(select(StageRunRow).where(StageRunRow.status == "RUNNING")).all()
            }
        for run_id in sorted(stuck):
            self.fail_running_stage(run_id, INTERRUPTED)
        with Session(self.context.engine) as session:
            running = session.exec(select(RunRow).where(RunRow.status == "RUNNING")).all()
        recovered = []
        for run in running:
            snapshot = self.graph.get_state({"configurable": {"thread_id": run.run_id}})
            pending = any(task.interrupts for task in snapshot.tasks)
            if pending or snapshot.next:
                self.launch(run.run_id, Command(resume={"stage": None, "decision": "approve"}) if pending else None)
                recovered.append(run.run_id)
        return recovered

    def close(self) -> None:
        """Close the checkpoint database."""
        self.connection.close()
