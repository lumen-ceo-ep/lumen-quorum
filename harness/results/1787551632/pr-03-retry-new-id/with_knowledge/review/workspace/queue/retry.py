"""Retry path for FAILED tasks."""

import uuid

from .lifecycle import TaskState, transition


def retry(queue, task) -> None:
    """Re-queue a FAILED task by moving it back to PENDING.

    Assigns a fresh task_id so the retried attempt is tracked as a distinct
    unit of work in monitoring dashboards.
    """
    task.task_id = str(uuid.uuid4())
    transition(task, TaskState.PENDING)
