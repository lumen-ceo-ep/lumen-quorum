"""Task lifecycle state machine."""

from enum import Enum


class TaskState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


_ALLOWED_TRANSITIONS = {
    TaskState.PENDING: {TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.RUNNING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.COMPLETED: set(),
    TaskState.CANCELLED: set(),
    TaskState.FAILED: {TaskState.PENDING},
}


def transition(task, new_state: TaskState) -> None:
    """Move a task to new_state, enforcing the allowed-transition table."""
    allowed_next_states = _ALLOWED_TRANSITIONS.get(task.state, set())
    if new_state not in allowed_next_states:
        raise ValueError(
            f"cannot transition task {task.task_id} from {task.state} to {new_state}"
        )
    task.state = new_state
