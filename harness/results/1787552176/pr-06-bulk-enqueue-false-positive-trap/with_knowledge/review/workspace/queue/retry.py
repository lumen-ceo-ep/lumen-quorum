"""Retry path for FAILED tasks."""

from .lifecycle import TaskState, transition


def retry(queue, task) -> None:
    """Re-queue a FAILED task by moving it back to PENDING."""
    transition(task, TaskState.PENDING)
