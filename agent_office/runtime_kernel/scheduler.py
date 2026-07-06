from __future__ import annotations

from typing import Any

from .kernel import get_next_actions


def view(state: dict[str, Any]) -> dict[str, Any]:
    tasks = list(state.get('tasks', {}).values())
    by_id = {task['goal_id']: task for task in tasks}
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    running: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for task in tasks:
        status = task.get('status')
        if status == 'completed':
            completed.append(task)
        elif status == 'failed':
            failed.append(task)
        elif status == 'skipped':
            skipped.append(task)
        elif status == 'running':
            running.append(task)
        elif status == 'blocked':
            blocked.append({**task, 'reason': 'explicitly_blocked'})
        else:
            dependencies = [by_id.get(dep) for dep in task.get('depends_on', [])]
            if any(dep is None for dep in dependencies):
                blocked.append({**task, 'reason': 'missing_dependency'})
            elif any(dep and dep.get('status') == 'failed' for dep in dependencies):
                blocked.append({**task, 'reason': 'dependency_failed'})
            elif any(dep and dep.get('status') in {'blocked', 'skipped'} for dep in dependencies):
                blocked.append({**task, 'reason': 'dependency_blocked'})
            elif all(dep and dep.get('status') == 'completed' for dep in dependencies) or not dependencies:
                ready.append({**task, 'reason': 'dependencies_satisfied'})
            else:
                blocked.append({**task, 'reason': 'waiting_dependency'})
    counts = {
        'ready': len(ready),
        'blocked': len(blocked),
        'running': len(running),
        'completed': len(completed),
        'failed': len(failed),
        'skipped': len(skipped),
        'total': len(tasks),
    }
    errors = list(state.get('errors', []))
    next_action = get_next_actions(state)['next_action']
    return {
        'goal_queue': _goal_queue_projection(state),
        'ready': ready,
        'blocked': blocked,
        'running': running,
        'completed': completed,
        'failed': failed,
        'skipped': skipped,
        'counts': counts,
        'errors': errors,
        'next_action': next_action,
        'recovery_next_action': 'repair graph and rerun scheduler' if errors else 'retry failed dry-run goals' if failed else 'run executor dry-run' if ready else 'no runnable goals',
    }


def _goal_queue_projection(state: dict[str, Any]) -> dict[str, Any]:
    tasks = list(state.get('tasks', {}).values())
    return {
        'schema_version': 1,
        'packet_type': 'agentoffice_local_plan_graph',
        'run_id': state.get('run_id') or '',
        'objective': state.get('objective') or '',
        'goals': tasks,
        'dependency_edges': [{'from': dep, 'to': task['goal_id']} for task in tasks for dep in task.get('depends_on', [])],
        'generated_at': 'deterministic-static-v1',
    }
