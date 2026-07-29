## Summary

## Verification

- [ ] Unit tests pass
- [ ] Offline planner evals pass
- [ ] Agent distribution validation passes
- [ ] Secret scan passes
- [ ] Wheel builds

## Paid-task safety

- [ ] Planning remains credential-free
- [ ] Inputs are validated before upload/task creation
- [ ] No automatic retry was added around paid creation
- [ ] New multi-job behavior is represented in `estimated_jobs` and respects `--max-jobs`

## Agent compatibility

- [ ] Canonical workflow remains in `skills/kie-media`
- [ ] Claude/Codex/Copilot adapters were updated only if discovery changed
