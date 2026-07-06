from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EVENT_TYPES = {
    'RUN_CREATED',
    'TASK_DEFINED',
    'TASK_READY',
    'TASK_STARTED',
    'TASK_COMPLETED',
    'TASK_FAILED',
    'TASK_SKIPPED',
    'MEMORY_RECORDED',
    'ARTIFACT_RECORDED',
    'VALIDATION_RECORDED',
}
STABLE_CREATED_AT = 'deterministic-static-v1'


class EventLogError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def event_log_path(workspace_root: Path) -> Path:
    return workspace_root / 'events.jsonl'


def ensure_event_log(path: Path) -> None:
    _assert_safe_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text('', encoding='utf-8')


def append_event(path: Path, *, run_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_event_log(path)
    if event_type not in EVENT_TYPES:
        raise EventLogError('runtime_event_type_invalid', f'Unsupported runtime event type: {event_type}')
    events = read_events(path)
    event = {
        'event_id': f'evt-{len(events) + 1:06d}',
        'run_id': run_id,
        'type': event_type,
        'payload': payload,
        'created_at': STABLE_CREATED_AT,
    }
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n')
    return event


def read_events(path: Path) -> list[dict[str, Any]]:
    _assert_safe_file(path)
    if not path.exists():
        raise EventLogError('runtime_event_log_missing', 'Runtime event log is missing.')
    events: list[dict[str, Any]] = []
    try:
        for index, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise EventLogError('runtime_event_log_jsonl_invalid', f'Event {index} must be an object.')
            events.append(event)
    except json.JSONDecodeError as exc:
        raise EventLogError('runtime_event_log_jsonl_unreadable', f'Unable to read runtime event log JSONL at line {index}.') from exc
    return events


def read_events_by_run_id(path: Path, run_id: str) -> list[dict[str, Any]]:
    return [event for event in read_events(path) if event.get('run_id') == run_id]


def _assert_safe_file(path: Path) -> None:
    if path.exists() and path.is_symlink():
        raise EventLogError('runtime_workspace_file_symlink_refused', f'Refusing symlink file: {path.name}')
    for parent in path.parents:
        if parent.exists() and parent.is_symlink():
            raise EventLogError('runtime_workspace_symlink_escape', f'Refusing symlink parent in event log path: {path}')
