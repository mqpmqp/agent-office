from __future__ import annotations

from pathlib import Path
from typing import Any

from .event_log import read_events_by_run_id
from .validator import validate_event, validate_replay_invariants, validate_transition


def reduce(events: list[dict[str, Any]]) -> dict[str, Any]:
    state: dict[str, Any] = {
        'run_id': None,
        'workspace': '',
        'objective': '',
        'tasks': {},
        'memory': [],
        'artifacts': [],
        'validations': [],
    }
    for event in events:
        validate_event(event)
        payload = event['payload']
        state['run_id'] = event['run_id']
        event_type = event['type']
        if event_type == 'RUN_CREATED':
            state['workspace'] = str(payload.get('workspace', state['workspace']))
            state['objective'] = str(payload.get('objective', state['objective']))
        elif event_type == 'TASK_DEFINED':
            task_id = str(payload['goal_id'])
            previous = state['tasks'].get(task_id, {})
            state['tasks'][task_id] = {**previous, **payload, 'goal_id': task_id, 'status': payload.get('status', 'pending')}
        elif event_type in {'TASK_READY', 'TASK_STARTED', 'TASK_COMPLETED', 'TASK_FAILED', 'TASK_SKIPPED'}:
            task_id = str(payload['goal_id'])
            task = dict(state['tasks'].get(task_id, {'goal_id': task_id, 'depends_on': []}))
            validate_transition(task.get('status'), event_type)
            task.update(payload)
            task['status'] = {
                'TASK_READY': 'pending',
                'TASK_STARTED': 'running',
                'TASK_COMPLETED': 'completed',
                'TASK_FAILED': 'failed',
                'TASK_SKIPPED': 'skipped',
            }[event_type]
            state['tasks'][task_id] = task
        elif event_type == 'MEMORY_RECORDED':
            state['memory'].append(payload)
        elif event_type == 'ARTIFACT_RECORDED':
            state['artifacts'].append(payload)
        elif event_type == 'VALIDATION_RECORDED':
            state['validations'].append(payload)
    state['errors'] = validate_replay_invariants(state)
    return state


def get_state(event_log_path: Path, run_id: str) -> dict[str, Any]:
    return reduce(read_events_by_run_id(event_log_path, run_id))


def get_next_actions(state: dict[str, Any]) -> dict[str, Any]:
    errors = list(state.get('errors', []))
    if errors:
        return {'next_action': 'repair_goal_graph', 'reason': 'replay_invariant_failed', 'errors': errors}
    tasks = state.get('tasks', {})
    ready = _ready_tasks(tasks)
    failed = [task for task in tasks.values() if task.get('status') == 'failed']
    blocked = _blocked_tasks(tasks)
    running = [task for task in tasks.values() if task.get('status') == 'running']
    if ready:
        return {'next_action': 'run_ready_goals', 'goal_ids': [task['goal_id'] for task in ready]}
    if failed:
        return {'next_action': 'inspect_failed', 'goal_ids': [task['goal_id'] for task in failed]}
    if blocked:
        return {'next_action': 'inspect_blocked', 'goal_ids': [task['goal_id'] for task in blocked]}
    if running:
        return {'next_action': 'inspect_running', 'goal_ids': [task['goal_id'] for task in running]}
    return {'next_action': 'complete', 'goal_ids': []}


def replay(event_log_path: Path, run_id: str) -> dict[str, Any]:
    state = get_state(event_log_path, run_id)
    state['next_action'] = get_next_actions(state)
    return state


def _ready_tasks(tasks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ready: list[dict[str, Any]] = []
    for task in tasks.values():
        if task.get('status') != 'pending':
            continue
        dependencies = [tasks.get(dep) for dep in task.get('depends_on', [])]
        if dependencies and all(dep and dep.get('status') == 'completed' for dep in dependencies):
            ready.append(task)
        if not dependencies:
            ready.append(task)
    return ready


def _blocked_tasks(tasks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for task in tasks.values():
        if task.get('status') != 'pending':
            continue
        dependencies = [tasks.get(dep) for dep in task.get('depends_on', [])]
        if any(dep is None or dep.get('status') in {'failed', 'blocked', 'skipped', 'pending', 'running'} for dep in dependencies):
            blocked.append(task)
    return blocked
