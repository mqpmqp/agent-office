from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_office.runtime_kernel.event_log import EventLogError, append_event, ensure_event_log, read_events, read_events_by_run_id
from agent_office.runtime_kernel.executor import execute
from agent_office.runtime_kernel.kernel import get_next_actions, get_state, replay
from agent_office.runtime_kernel.scheduler import view
from agent_office.runtime_kernel.validator import validate_event


class RuntimeKernelTests(unittest.TestCase):
    def test_event_log_append_read_and_run_filter_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            event = append_event(path, run_id="run-a", event_type="RUN_CREATED", payload={"workspace": ".ai/run-a"})
            append_event(path, run_id="run-b", event_type="RUN_CREATED", payload={"workspace": ".ai/run-b"})

            self.assertEqual(event["event_id"], "evt-000001")
            self.assertEqual(event["created_at"], "deterministic-static-v1")
            self.assertEqual(len(read_events(path)), 2)
            self.assertEqual(len(read_events_by_run_id(path, "run-a")), 1)

    def test_kernel_reduce_replay_and_next_action_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            append_event(path, run_id="run-a", event_type="RUN_CREATED", payload={"workspace": ".ai/run-a", "objective": "demo"})
            append_event(path, run_id="run-a", event_type="TASK_DEFINED", payload={"goal_id": "plan", "agent_role": "planner", "status": "pending", "depends_on": []})
            first = replay(path, "run-a")
            second = replay(path, "run-a")

            self.assertEqual(first, second)
            self.assertEqual(first["tasks"]["plan"]["status"], "pending")
            self.assertEqual(get_next_actions(first)["next_action"], "run_ready_goals")

    def test_memory_and_workspace_are_projections_not_state_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "events.jsonl"
            append_event(path, run_id="run-a", event_type="RUN_CREATED", payload={"workspace": ".ai/run-a"})
            append_event(path, run_id="run-a", event_type="MEMORY_RECORDED", payload={"memory_id": "mem-0001", "agent_role": "planner"})
            (root / "memory.jsonl").write_text("{not-json\n", encoding="utf-8")

            state = get_state(path, "run-a")
            self.assertEqual(state["memory"][0]["memory_id"], "mem-0001")
            self.assertEqual(state["workspace"], ".ai/run-a")

    def test_scheduler_view_is_pure_projection(self) -> None:
        state = {
            "run_id": "run-a",
            "tasks": {
                "done": {"goal_id": "done", "status": "completed", "depends_on": []},
                "ready": {"goal_id": "ready", "status": "pending", "depends_on": ["done"]},
            },
            "errors": [],
        }
        before = json.dumps(state, sort_keys=True)
        projected = view(state)
        after = json.dumps(state, sort_keys=True)

        self.assertEqual(before, after)
        self.assertEqual(projected["counts"]["ready"], 1)
        self.assertEqual(projected["next_action"], "run_ready_goals")

    def test_executor_emits_events_without_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.jsonl"
            append_event(path, run_id="run-a", event_type="RUN_CREATED", payload={"workspace": ".ai/run-a"})
            append_event(path, run_id="run-a", event_type="TASK_DEFINED", payload={"goal_id": "plan", "agent_role": "planner", "status": "pending", "depends_on": []})
            events = execute(path, run_id="run-a", task={"goal_id": "plan", "agent_role": "planner"}, worker_slot=1)

            self.assertEqual([event["type"] for event in events], ["TASK_STARTED", "TASK_COMPLETED"])
            self.assertNotIn("next_action", events[-1]["payload"])
            self.assertEqual(get_state(path, "run-a")["tasks"]["plan"]["status"], "completed")

    def test_invalid_event_type_raises_stable_error(self) -> None:
        with self.assertRaises(EventLogError) as error:
            validate_event({
                "event_id": "evt-invalid",
                "run_id": "run-a",
                "type": "NOT_A_RUNTIME_EVENT",
                "payload": {},
            })

        self.assertEqual(error.exception.error_code, "runtime_event_type_invalid")

    def test_missing_bad_json_and_symlink_event_log_fail_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            missing = root / "missing.jsonl"
            bad = root / "bad.jsonl"
            bad.write_text("{bad\n", encoding="utf-8")
            target = root / "target.jsonl"
            target.write_text("", encoding="utf-8")
            link = root / "link.jsonl"
            link.symlink_to(target)

            with self.assertRaises(EventLogError) as missing_error:
                read_events(missing)
            with self.assertRaises(EventLogError) as bad_error:
                read_events(bad)
            with self.assertRaises(EventLogError) as link_error:
                ensure_event_log(link)

        self.assertEqual(missing_error.exception.error_code, "runtime_event_log_missing")
        self.assertEqual(bad_error.exception.error_code, "runtime_event_log_jsonl_unreadable")
        self.assertEqual(link_error.exception.error_code, "runtime_workspace_file_symlink_refused")


if __name__ == "__main__":
    unittest.main()
