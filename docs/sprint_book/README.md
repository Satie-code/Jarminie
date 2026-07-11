# Sprint Book

**Start at [INDEX.md](INDEX.md)** — the Master Sprint Book index for all of Version 1: every level, phase, and sprint, with numbering, dependencies, complexity estimates, and milestone versions.

## Numbering

Sprint ID = `<Level>.<SequentialIndex>` (e.g. `1.1`, `1.2`, ... `2.1`, `2.2`, ...). The index restarts at 1 per Level and increments once per sprint, independent of Part 4's Phase numbers — a single Phase can span several sprints when it bundles more than one subsystem/feature (see the Sprint Size rule in [05_Claude_Development_Guide.md](../05_Claude_Development_Guide.md)). File naming: `sprint_<level>_<index>.md`.

## File Structure

Each sprint file follows the exact template from [05_Claude_Development_Guide.md](../05_Claude_Development_Guide.md): Sprint ID, Sprint Name, Purpose, Objectives, Engineering Rationale, Prerequisites, Dependencies, Files to Create, Files to Modify, Expected Classes, Expected Interfaces, Expected Functions, Implementation Tasks, Architecture Notes, Potential Risks, Acceptance Criteria, Testing Checklist, Documentation Checklist, Definition of Done, Estimated Complexity, Estimated Development Time, Next Sprint, Future Considerations. Once a sprint is actually implemented, its Sprint Completion Report (Step 10 of the guide — Summary, Files Created, Files Modified, Tests Added, Documentation Updated, Acceptance Criteria ✔/✖, Risks, Technical Debt, Recommendations) is appended to the same file.

## Detail Status

Level 1 (sprints 1.1–1.9) is fully specified. Levels 2–6 exist at roadmap/index granularity in [INDEX.md](INDEX.md) only, by design — see the Detail Status note there for why.
