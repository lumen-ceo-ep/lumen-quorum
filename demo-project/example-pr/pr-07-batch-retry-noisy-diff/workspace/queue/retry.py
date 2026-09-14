"""Retry path for FAILED tasks."""

import uuid

from .lifecycle import TaskState, transition


def retry(queue, task) -> None:
    """Re-queue a FAILED task by moving it back to PENDING."""
    transition(task, TaskState.PENDING)


def retry_many(queue, tasks) -> None:
    """Re-queue several FAILED tasks in one batch call.

    Each retried task is assigned a fresh task_id so that concurrent retries
    submitted in the same batch can never collide on identifier, then the
    task is moved back to PENDING the same way a single retry() would.
    """
    for task in tasks:
        task.task_id = str(uuid.uuid4())
        transition(task, TaskState.PENDING)
