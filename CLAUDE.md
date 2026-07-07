# CLAUDE.md

## PR Rules

- One concern per PR. One layer of the stack per PR. Do not bundle cross-layer changes.
- If a PR is growing large, stop and split it.
- Every PR needs a one-sentence description of scope.
- Terse commit messages: what changed and why. One line preferred.
- If review is backed up, pause and flag the jam — do not open more PRs into the pile.

## Micro-Block Format

Before opening a multi-PR feature, document the plan as a checklist in the relevant issue first:

```
[ ] repo: what this PR does
[ ] repo: what the next PR does
```

Check off as PRs merge. Keep the list in the issue, not buried in a PR description.

## Communication

- Use low verbosity. Plain, simple English only. No jargon unless necessary.
- Before starting any planned work, ask detailed questions first. Keep the questions easy to understand — no assumed context.

## Writing Code

- Never write a full script in one go.
- Start with a bare framework only. Then add one feature at a time.
- Each addition should be reviewed and confirmed before moving to the next.
- Use the simplest code that works. No clever solutions, no over-engineering.
- No code bloat. If it isn't needed, cut it.
- Comments only where absolutely necessary. Keep them short and plain.
- Test and confirm each feature works before building the next one on top of it.
- Do not add a library or dependency unless plain code cannot do the job. Every dependency needs a stated reason.
- Do not create new files or folders unless necessary. When in doubt, ask first.
- If stuck, stop and ask. Do not hack around a problem — a wrong solution that works is still wrong.
- Never hardcode credentials, paths, or environment-specific values. Ask where they should live if unsure.

## Default Stance

Read the code. Understand before touching. Doing nothing in deliverables is valid and often preferable when bandwidth is low. Small and shippable beats complete and blocked.
