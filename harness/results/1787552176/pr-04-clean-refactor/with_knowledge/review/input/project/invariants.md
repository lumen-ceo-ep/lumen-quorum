# Invariants — demo-project

A fictional small task-queue service, invented purely to give M0 something concrete to
backtest against.

## INV-1
A task in `CANCELLED` state must never transition to `RUNNING`. (source: design.md#lifecycle)

## INV-2
`enqueue()` must reject a task whose `priority` is outside `[0, 9]` rather than clamping
it silently. (source: design.md#priority-validation)

## INV-3
Retrying a task must reuse its original `task_id`; a retry must never allocate a new id,
since downstream consumers dedupe on `task_id`. (source: design.md#retry-semantics)
