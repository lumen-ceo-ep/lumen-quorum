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
    TaskState.CANCELLED: {TaskState.RUNNING},  # allow re-activating a cancelled task
    TaskState.FAILED: {TaskState.PENDING},  # retry re-queues a failed task
}


def transition(task, new_state: TaskState) -> None:
    """Move a task to new_state, enforcing the allowed-transition table.

    A CANCELLED task has no outgoing transitions: cancellation is terminal
    (INV-1). Raises ValueError on a disallowed transition.
    """
    allowed = _ALLOWED_TRANSITIONS.get(task.state, set())
    if new_state not in allowed:
        raise ValueError(
            f"cannot transition task {task.task_id} from {task.state} to {new_state}"
        )
    task.state = new_state
