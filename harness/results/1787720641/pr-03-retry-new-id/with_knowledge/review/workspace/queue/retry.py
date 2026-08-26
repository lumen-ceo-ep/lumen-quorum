"""Retry path for FAILED tasks."""

import uuid

from .lifecycle import TaskState, transition


def retry(queue, task) -> None:
    """Re-queue a FAILED task, assigning a fresh id to the retried attempt."""
    task.task_id = str(uuid.uuid4())
    transition(task, TaskState.PENDING)
