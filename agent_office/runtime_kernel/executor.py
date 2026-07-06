from __future__ import annotations

from pathlib import Path
from typing import Any

from .event_log import append_event


def execute(event_log_path: Path, *, run_id: str, task: dict[str, Any], worker_slot: int, fail: bool = False) -> list[dict[str, Any]]:
    goal_id = str(task['goal_id'])
    events = [append_event(event_log_path, run_id=run_id, event_type='TASK_STARTED', payload={'goal_id': goal_id, 'worker_slot': worker_slot})]
    result = {
        'goal_id': goal_id,
        'agent_role': task.get('agent_role', 'executor'),
        'worker_slot': worker_slot,
        'status': 'failed' if fail else 'dry_run_completed',
        'classification': 'simulated_failure' if fail else 'safe_local_simulation',
        'shell_executed': False,
        'provider_calls': False,
        'model_calls': False,
    }
    if fail:
        events.append(append_event(event_log_path, run_id=run_id, event_type='TASK_FAILED', payload={**result, 'status': 'failed'}))
    else:
        events.append(append_event(event_log_path, run_id=run_id, event_type='TASK_COMPLETED', payload={**result, 'status': 'completed'}))
    return events
