"""Canonical long-term domain registry for the FUGU-like framework.

This module is the single source of truth for the framework's core domain
vocabulary: core object names, standard roles, provider names, and the goal
and task state machines. It is pure data plus pure functions: no I/O, no
environment reads, no provider calls, no imports beyond the standard library.

Normative documentation: docs/AGENTOFFICE_FUGU_LIKE_FRAMEWORK.md.
"""

from __future__ import annotations

SCHEMA_VERSION = 1

PRODUCT_NAME = "AgentOffice"
ARCHITECTURE_TARGET = "local-first multi-agent office runtime"
RUNTIME_MODEL = "deterministic_cli_tick_first"

# Core domain objects (framework doc section 3). Order is the canonical
# presentation order used by machine-readable status output.
CORE_OBJECTS: tuple[str, ...] = (
    "workspace",
    "goal",
    "task_graph",
    "role",
    "agent",
    "provider",
    "packet",
    "run",
    "runtime_event",
    "actor_result",
    "evidence_bundle",
    "review",
    "gate_decision",
    "archive",
)

# Roles are responsibilities, never vendors (framework doc section 6).
STANDARD_ROLES: tuple[str, ...] = (
    "context_agent",
    "planner_agent",
    "implementation_agent",
    "review_agent",
    "judge_agent",
    "delivery_agent",
    "human_approver",
    "external_worker",
)

# Providers are replaceable implementations behind a role. Real provider
# calls are disabled by default and require explicit authorization.
KNOWN_PROVIDERS: tuple[str, ...] = (
    "manual",
    "local_mock",
    "codex",
    "claude",
    "gemini",
    "grok",
)

GOAL_STATES: tuple[str, ...] = (
    "goal.created",
    "goal.planned",
    "goal.packetized",
    "goal.running",
    "goal.review_pending",
    "goal.gate_pending",
    "goal.passed",
    "goal.failed",
    "goal.archived",
)

TASK_STATES: tuple[str, ...] = (
    "task.created",
    "task.ready",
    "task.dispatched",
    "task.result_pending",
    "task.result_received",
    "task.review_pending",
    "task.accepted",
    "task.rejected",
    "task.blocked",
    "task.skipped",
)

REVIEW_VERDICTS: tuple[str, ...] = ("pass", "conditional_pass", "fail")

GATE_DECISIONS: tuple[str, ...] = (
    "allow_merge",
    "block_merge",
    "require_fix",
    "require_human",
)

# Ordered implementation slices that follow the framework reset
# (migration plan section 2).
NEXT_SLICES: tuple[str, ...] = (
    "workspace_store",
    "runtime_event_log",
    "task_graph_kernel",
    "packet_result_intake",
    "review_gate_v2",
)

ARTIFACT_REVIEW_CAVEAT = (
    "Claude did not execute commands unless it actually ran them in the correct repo. "
    "Validation outputs from VPS are evidence artifacts, not Claude-executed proof."
)


def is_valid_goal_state(state: str) -> bool:
    return state in GOAL_STATES


def is_valid_task_state(state: str) -> bool:
    return state in TASK_STATES


def is_valid_role(role: str) -> bool:
    return role in STANDARD_ROLES
