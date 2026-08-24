"""Retry path for FAILED tasks."""

from .lifecycle import TaskState, transition


def retry(queue, task) -> None:
    """Re-queue a FAILED task by moving it back to PENDING.

    Reuses the task's existing task_id (INV-3): downstream consumers dedupe
    completed work by task_id, so a retry that allocated a new id would look
    like unrelated new work rather than a retry of the same task.
    """
    transition(task, TaskState.PENDING)
