# P8 Claude Review Fix Report

## Summary

- Branch: `phase8/p8-batch-completion`
- Starting commit: `7648e6bf42a009e8f1e3fa8b90d1593dfb4fb7e3`
- Claude verdict: `needs changes (minor)`
- Claude marker received: `P8_CLAUDE_REVIEW_COMPLETE`
- Fix status: complete
- Commit: created after this report is staged; immutable commit SHA is reported in the final completion response.
- Origin branch HEAD: set by the post-report push; immutable remote HEAD is reported in the final completion response.

## Claude Findings Addressed

1. Confined the `P6-PROFILES -> P6-17` alias to the explicit `run-bundle preview` action only.
   - `run-bundle preview --objective P6-PROFILES --profile lowest-cost --json` still passes.
   - The preview payload keeps `run_id=P6-PROFILES` and resolves the static objective/plan to `P6-17`.
   - The implicit no-action build path rejects `P6-PROFILES` with exit `2` and no traceback.
2. Added regression coverage for:
   - preview alias positive behavior;
   - implicit build rejection of `P6-PROFILES`;
   - `preview --out` writing a complete bundle and reporting `artifact_writes=true`;
   - `preview --run-id CUSTOM-RID` preserving the explicit run id.
3. Updated `P8_BATCH_COMPLETION_REPORT.md` to clarify:
   - the alias is scoped to explicit `run-bundle preview` only;
   - handoff smoke PASS depends on the local untracked `.ai/runs/P8-HANDOFF` bundle;
   - symlink negative behavior is a symlink/path refusal, not an argparse usage contract.

## Changed Files

- `agent_office/cli.py`
- `agent_office/run_bundle.py`
- `tests/test_run_bundle_cli.py`
- `P8_BATCH_COMPLETION_REPORT.md`
- `P8_CLAUDE_REVIEW_FIX_REPORT.md`

## Implementation Notes

- `run_bundle_preview_payload()` now accepts keyword-only `allow_alias=False`.
- `cmd_run_bundle()` passes `allow_alias=True` only for explicit `run-bundle preview`.
- The implicit build path keeps `allow_alias=False` and therefore uses the static objective registry without the P6 smoke/staged alias.
- No new runtime/provider/adapter capability was added.

## Tests Added Or Updated

- `RunBundleCliTests::test_run_bundle_implicit_build_rejects_profiles_smoke_alias_without_traceback`
- `RunBundleCliTests::test_run_bundle_preview_action_writes_full_bundle_and_reports_artifacts`
- `RunBundleCliTests::test_run_bundle_preview_action_preserves_explicit_run_id`
- Existing preview alias positive coverage remains in `test_run_bundle_preview_action_accepts_profiles_smoke_alias_without_writes`.

## Positive Validation Results

- `python3 -m compileall agent_office tests`: PASS
- `python3 -m unittest`: PASS (`Ran 236 tests`)
- `python3 -m unittest discover -s tests -p 'test_*.py'`: PASS (`Ran 236 tests`)
- focused run-bundle CLI tests, `python3 -m unittest tests.test_run_bundle_cli -q`: PASS (`Ran 48 tests`)
- `python3 -m agent_office run-bundle preview --objective P6-PROFILES --profile lowest-cost --json`: PASS, payload contains `P6-PROFILES` and resolves objective data to `P6-17`
- `python3 -m agent_office run-bundle preview --objective P6-17 --profile lowest-cost --run-id CUSTOM-RID --json`: PASS, explicit run id preserved
- `python3 -m agent_office run-bundle preview --objective P6-17 --profile lowest-cost --out .ai/runs/P8-PREVIEW-FIX --json`: PASS, complete bundle written and `artifact_writes=true`; validation artifact was removed after the check
- JSON handoff smoke: PASS because local untracked `.ai/runs/P8-HANDOFF` exists on this VPS
- Human-readable handoff smoke: PASS because local untracked `.ai/runs/P8-HANDOFF` exists on this VPS

## Negative Validation Results

- `python3 -m agent_office run-bundle --objective P6-PROFILES --profile lowest-cost --run-id MYBUILD --json`: exit `2`, no traceback, error `Unknown objective: P6-PROFILES`
- Missing handoff bundle `.ai/runs/P8-HANDOFF-MISSING`: exit `2`, no traceback
- Path traversal handoff bundle `../outside-bundle`: exit `2`, no traceback
- Symlink handoff bundle `.ai/runs/P8-HANDOFF-SYMLINK-FIX`: exit `2`, no traceback, error `Refusing symlink run bundle path`

## Handoff Reproducibility Note

- `.ai/runs/P8-HANDOFF` is a local untracked run bundle artifact on this VPS.
- JSON and human-readable handoff smoke checks were run because that local bundle exists.
- This fix does not create or modify `.ai/runs/P8-HANDOFF`.

## Safety Boundary Confirmation

- `.env` read: no
- Environment variables printed: no
- Provider external behavior triggered: no
- Runtime or real runner triggered: no
- Adapter external behavior triggered: no
- Artifact content executed: no
- Historical untracked reports/audit bundles deleted, modified, or committed: no
- Tag created: no
- Default branch changed: no
- Force push performed: no
- Unrelated files modified: no

## Final Marker

P8_CLAUDE_REVIEW_FIX_COMPLETE
