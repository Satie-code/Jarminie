"""Unit tests for workflow.workflow_model."""

from datetime import UTC, datetime

from device_control.action_engine import ActionType
from workflow.workflow_model import WorkflowDefinition, WorkflowStep


def test_workflow_step_defaults():
    step = WorkflowStep(
        step_index=0,
        action_type=ActionType.LAUNCH_APPLICATION,
        parameters={"executable_path": "notepad.exe"},
        description="Open Notepad",
    )
    assert step.continue_on_failure is False


def test_workflow_step_continue_on_failure_can_be_set():
    step = WorkflowStep(
        step_index=1,
        action_type=ActionType.FILE_DELETE,
        parameters={"path": "a.txt"},
        description="Delete scratch file",
        continue_on_failure=True,
    )
    assert step.continue_on_failure is True


def test_workflow_definition_defaults_to_enabled():
    definition = WorkflowDefinition(
        workflow_id="wf-1",
        name="Continue Project JARMINEI",
        steps=[],
        created_by="user",
        created_at=datetime.now(UTC),
    )
    assert definition.is_enabled is True


def test_workflow_definition_preserves_step_order():
    steps = [
        WorkflowStep(
            step_index=i,
            action_type=ActionType.WINDOW_FOCUS,
            parameters={"handle": i},
            description=f"Step {i}",
        )
        for i in range(3)
    ]
    definition = WorkflowDefinition(
        workflow_id="wf-2",
        name="Ordered",
        steps=steps,
        created_by="user",
        created_at=datetime.now(UTC),
    )
    assert [step.step_index for step in definition.steps] == [0, 1, 2]
