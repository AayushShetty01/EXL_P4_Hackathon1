"""The five stage pipeline with a human gate after every stage, as a LangGraph state graph.

Nodes in order: discover, gate, document, gate, redevelop, gate, validate, gate, monitor, gate, done.
A gate pauses the run with interrupt() until a decision is recorded; the run id is the LangGraph thread
id and a SQLite checkpointer keeps paused runs across restarts. Stage and gate states live in the
factory_core database, which is what the API reads and what the routing below checks.
"""

from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlmodel import Session

from app.agents.compliance_matrix import build_compliance
from app.artifact_store import write_json_artifact
from app.audit_trail import AuditRecorder
from app.database import ModelRow, RunRow, utc_timestamp
from app.gate_decisions import record_automatic_approval
from app.pipeline_context import PipelineContext, StageFunction, execute_stage, stage_status
from app.pipeline_stages import discover_stage, document_stage, redevelop_stage
from app.schemas import STAGE_NAMES
from app.validation_lab_stages import monitor_stage, validate_stage

STAGE_WORK: dict[str, StageFunction] = {
    "discover": discover_stage,
    "document": document_stage,
    "redevelop": redevelop_stage,
    "validate": validate_stage,
    "monitor": monitor_stage,
}
DONE = "done"


class PipelineState(TypedDict):
    """What LangGraph keeps per run: only the run id; everything else is in the database."""

    run_id: str


def next_node(stage: str) -> str:
    """The stage after this one, or done after the last stage."""
    position = STAGE_NAMES.index(stage)
    return STAGE_NAMES[position + 1] if position + 1 < len(STAGE_NAMES) else DONE


def gate_name(stage: str) -> str:
    """Node name of the gate after a stage."""
    return f"gate_{stage}"


def stage_node(context: PipelineContext, stage: str) -> Callable[[PipelineState], dict[str, Any]]:
    """A node that runs one stage through its lifecycle."""

    def run_stage(state: PipelineState) -> dict[str, Any]:
        """Execute the stage; a finished stage is not executed again."""
        execute_stage(context, state["run_id"], stage, STAGE_WORK[stage])
        return {}

    return run_stage


def route_after_stage(context: PipelineContext, stage: str) -> Callable[[PipelineState], str]:
    """Go to the gate when the stage awaits review, past it when skipped, and stop on anything else."""

    def route(state: PipelineState) -> str:
        """Pick the next node from the stage status."""
        status = stage_status(context.engine, state["run_id"], stage)
        if status == "AWAITING_REVIEW":
            return gate_name(stage)
        return next_node(stage) if status == "SKIPPED" else END

    return route


def gate_node(context: PipelineContext, stage: str) -> Callable[[PipelineState], dict[str, Any]]:
    """A node that pauses the run until a human decision is recorded (or approves seeding runs)."""

    def wait_for_decision(state: PipelineState) -> dict[str, Any]:
        """Pause while the stage awaits review; a resume without a recorded decision pauses again."""
        run_id = state["run_id"]
        while stage_status(context.engine, run_id, stage) == "AWAITING_REVIEW":
            with Session(context.engine) as session:
                automatic = session.get(RunRow, run_id).auto_approve
            if automatic:
                record_automatic_approval(context.engine, run_id, stage)
            else:
                interrupt({"run_id": run_id, "stage": stage})
        return {}

    return wait_for_decision


def route_after_gate(context: PipelineContext, stage: str) -> Callable[[PipelineState], str]:
    """Continue after an approval; stop after a rejection."""

    def route(state: PipelineState) -> str:
        """Pick the next node from the gate decision."""
        return next_node(stage) if stage_status(context.engine, state["run_id"], stage) == "APPROVED" else END

    return route


def done_node(context: PipelineContext) -> Callable[[PipelineState], dict[str, Any]]:
    """The last node: complete the run and save the compliance matrix of the model."""

    def complete_run(state: PipelineState) -> dict[str, Any]:
        """Mark the run COMPLETED and write artifacts/{model_id}/compliance/ss123_matrix.json."""
        run_id = state["run_id"]
        with Session(context.engine) as session:
            run = session.get(RunRow, run_id)
            model_id = run.model_id
            run.status, run.current_stage, run.finished_at = "COMPLETED", None, utc_timestamp()
            session.add(run)
            session.commit()
            compliance = build_compliance(session, session.get(ModelRow, model_id)).model_dump(mode="json")
        recorder = AuditRecorder(context.engine, model_id=model_id, run_id=run_id)
        path = f"artifacts/{model_id}/compliance/ss123_matrix.json"
        write_json_artifact(context.settings, recorder, path, compliance)
        return {}

    return complete_run


def build_pipeline_graph(context: PipelineContext, checkpointer: Any) -> Any:
    """Wire the stages, gates and routing into a compiled graph that checkpoints every step."""
    graph = StateGraph(PipelineState)
    for stage in STAGE_NAMES:
        graph.add_node(stage, stage_node(context, stage))
        graph.add_node(gate_name(stage), gate_node(context, stage))
        graph.add_conditional_edges(stage, route_after_stage(context, stage), [gate_name(stage), next_node(stage), END])
        graph.add_conditional_edges(gate_name(stage), route_after_gate(context, stage), [next_node(stage), END])
    graph.add_node(DONE, done_node(context))
    graph.add_edge(START, STAGE_NAMES[0])
    graph.add_edge(DONE, END)
    return graph.compile(checkpointer=checkpointer)
