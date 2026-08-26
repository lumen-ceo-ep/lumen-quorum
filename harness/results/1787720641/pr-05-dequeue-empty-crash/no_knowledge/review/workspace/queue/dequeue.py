"""Task dequeue path."""

from .lifecycle import TaskState


def dequeue(queue):
    """Remove and return the highest-priority PENDING task."""
    pending = [t for t in queue if t.state == TaskState.PENDING]
    best = max(pending, key=lambda t: t.priority)
    queue.remove(best)
    return best
