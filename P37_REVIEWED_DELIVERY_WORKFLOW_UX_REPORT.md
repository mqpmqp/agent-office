# P37 Reviewed Delivery Workflow UX Report

Status: feature branch prepared for P37 reviewed-delivery workflow UX hardening.

Purpose:
- Promote the P36 end-to-end reviewed-delivery lifecycle from a test-only chain into a reusable CLI workflow.
- Keep the workflow static, local, and auditable.
- Preserve codex-deliver as the only command that performs real merge/push.

Implementation delta:
- Added `python3 -m agent_office review reviewed-delivery`.
- The command verifies a saved review output with `review attest`, generates a merge packet with `review merge-packet`, and runs `review codex-deliver` for safe preview or authorized delivery.
- JSON and text output are supported.
- Safe-mode is the default; authorized merge/push requires both `--merge-authorized --push-authorized`.
- Added focused tests for safe preview, missing authorization, readiness failure, stale target, successful authorized delivery, text output, and bad/missing review output.

Safety boundaries:
- `.env` not read.
- Env vars not printed.
- Provider/model/runtime/adapter external behavior not triggered.
- No default branch setting change.
- No force push.
- No tag.
- Real merge/push remains delegated only to `review codex-deliver`.

Marker:
P37_REVIEWED_DELIVERY_WORKFLOW_UX_FEATURE_READY
