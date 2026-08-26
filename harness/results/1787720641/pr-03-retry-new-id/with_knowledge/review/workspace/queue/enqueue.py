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
    """Add a new PENDING task to the queue."""
    if not (MIN_PRIORITY <= priority <= MAX_PRIORITY):
        raise InvalidPriorityError(
            f"priority {priority} outside [{MIN_PRIORITY}, {MAX_PRIORITY}]"
        )
    task = Task(task_id=task_id, priority=priority, state=TaskState.PENDING)
    queue.append(task)
    return task
