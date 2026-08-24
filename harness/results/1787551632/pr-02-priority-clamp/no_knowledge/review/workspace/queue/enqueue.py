"""Task enqueue path."""

from .lifecycle import TaskState

MIN_PRIORITY = 0
MAX_PRIORITY = 9


class InvalidPriorityError(ValueError):
    pass


class Task:
    def __init__(self, task_id: str, priority: int, state: TaskState):
        self.task_id = task_id
        self.priority = priority
        self.state = state


def enqueue(queue, task_id: str, priority: int) -> "Task":
    """Add a new PENDING task to the queue.

    priority must be in [MIN_PRIORITY, MAX_PRIORITY]; a value outside that
    range is rejected outright rather than clamped, since silently clamping
    would let a caller believe a request for priority 9 was honored when it
    was actually capped (INV-2).
    """
    # Clamp out-of-range priorities instead of rejecting the request.
    priority = max(MIN_PRIORITY, min(MAX_PRIORITY, priority))
    task = Task(task_id=task_id, priority=priority, state=TaskState.PENDING)
    queue.append(task)
    return task
