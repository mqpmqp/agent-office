from __future__ import annotations

from typing import Any

from .event_log import EVENT_TYPES, EventLogError


TERMINAL_TASK_EVENTS = {'TASK_COMPLETED', 'TASK_FAILED', 'TASK_SKIPPED'}


def validate_event(event: dict[str, Any]) -> None:
    for field in ('event_id', 'run_id', 'type', 'payload'):
        if field not in event:
            raise EventLogError('runtime_event_invalid', f'Runtime event missing field: {field}')
    if event['type'] not in EVENT_TYPES:
        raise EventLogError('runtime_event_type_invalid', f'Unsupported runtime event type: {event[ type]}')
    if not isinstance(event['payload'], dict):
        raise EventLogError('runtime_event_payload_invalid', 'Runtime event payload must be an object.')


def validate_transition(prior_status: str | None, event_type: str) -> None:
    if prior_status in {'completed', 'failed', 'skipped'} and event_type in {'TASK_STARTED', *TERMINAL_TASK_EVENTS}:
        raise EventLogError('runtime_task_transition_invalid', f'Cannot transition terminal task with {event_type}.')


def validate_replay_invariants(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tasks = state.get('tasks', {})
    if not isinstance(tasks, dict):
        return ['tasks_not_object']
    for task_id, task in tasks.items():
        for dependency in task.get('depends_on', []):
            if dependency not in tasks:
                errors.append(f'missing_dependency:{task_id}->{dependency}')
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str, path: list[str]) -> None:
        if task_id in visiting:
            errors.append('circular_dependency:' + '->'.join([*path, task_id]))
            return
        if task_id in visited or task_id not in tasks:
            return
        visiting.add(task_id)
        for dependency in tasks[task_id].get('depends_on', []):
            visit(dependency, [*path, task_id])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id, [])
    return sorted(set(errors))
