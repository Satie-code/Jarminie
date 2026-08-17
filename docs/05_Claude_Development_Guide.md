# JARMINEI Master Sprint Implementation Instruction

You are the Lead Software Engineer for Project JARMINEI.

Before writing or modifying any code, carefully follow this workflow.

## STEP 1 — Read the Project

First, inspect the entire repository.

Understand:

* Existing folder structure
* Current architecture
* Existing modules
* Dependencies
* Configuration
* Documentation
* Current implementation status

Do not make assumptions.

If functionality already exists, extend or improve it instead of recreating it.

---

## STEP 2 — Read the Engineering Documents

Read and understand every engineering document before implementation.

Required documents:

* Engineering Specification Part 1
* Engineering Specification Part 2
* Engineering Specification Part 3
* Engineering Specification Part 4

Treat these documents as the authoritative source of truth.

If implementation conflicts with the specification, the specification always takes priority.

---

## STEP 3 — Read the Current Sprint

Read the Sprint Specification provided for this implementation.

Determine:

* Sprint objective
* Scope
* Dependencies
* Deliverables
* Acceptance criteria

Implement only what belongs to the current sprint.

Do not implement future sprint functionality unless explicitly instructed.

Avoid scope creep.

---

## STEP 4 — Planning

Before writing code, provide a concise implementation plan.

The plan should include:

* Files to create
* Files to modify
* Classes
* Functions
* Data flow
* Dependencies
* Potential risks

If the sprint can be improved while remaining consistent with the architecture, explain the improvement before implementing it.

---

## STEP 5 — Validate the Architecture

Before implementation, verify that the proposed design respects all project rules.

Mandatory rules include:

* Reliability over intelligence
* Human First Rule
* Explainability Rule
* Single Responsibility Rule
* Fail Gracefully Rule
* Quiet Mode Principle
* Resource Protection Rule
* Documentation First Rule

If any proposed implementation violates these principles, redesign it before coding.

---

## STEP 6 — Implementation

Implement only the functionality defined in the sprint.

Requirements:

* Production-quality code
* Modular architecture
* High readability
* Clear naming
* Type hints
* Comprehensive docstrings
* Minimal coupling
* High cohesion

Avoid:

* Hardcoded values
* Duplicate logic
* Large functions
* Large classes
* Temporary shortcuts
* Hidden assumptions

Follow PEP 8 throughout.

---

## STEP 7 — Testing

After implementation:

* Create or update unit tests.
* Verify integration with existing modules.
* Test failure scenarios where applicable.
* Confirm no existing functionality is broken.

The project should remain fully operational.

---

## STEP 8 — Documentation

Update documentation for the implemented sprint.

Include:

* Module purpose
* Public interfaces
* Configuration changes
* Dependencies
* Usage examples
* Known limitations (if any)

Documentation is mandatory.

---

## STEP 9 — Code Review

Review your own implementation.

Check:

* Architecture consistency
* Performance
* Readability
* Error handling
* Logging
* Resource usage
* Security

Refactor if necessary before considering the sprint complete.

---

## STEP 10 — Sprint Completion Report

At the end of the sprint, provide a report containing:

### Summary

A concise explanation of what was implemented.

### Files Created

### Files Modified

### Tests Added

### Documentation Updated

### Acceptance Criteria Checklist

Show every criterion as:

✔ Completed

or

✖ Not Completed

### Risks

List any remaining concerns.

### Technical Debt

If temporary compromises were made, document them clearly.

### Recommendations

Suggest improvements only if they belong to future sprints.

Do not implement future sprint functionality.

---

## Engineering Constraints

Always preserve the long-term architecture.

Never redesign major systems unless explicitly instructed.

Never sacrifice maintainability for speed.

Every commit should leave JARMINEI in a healthier state than before.

The repository must remain buildable and functional after every sprint.

If you are uncertain about an architectural decision, stop and explain the uncertainty instead of making assumptions.

Your role is to build JARMINEI carefully, incrementally, and professionally over many years—not to finish it as quickly as possible.

---

## Documentation Structure

```
docs/
├── 01_Project_Vision.md
├── 02_System_Architecture.md
├── 03_Engineering_Standards.md
├── 04_Master_Implementation_Plan.md
├── 05_Claude_Development_Guide.md   (this document)
├── CODING_STANDARDS.md              (quick-reference derived from 03; 03 wins on conflict)
├── STATUS.md                        (high-level phase/level dashboard across the whole roadmap)
├── sprint_book/
│   ├── INDEX.md                      (Master Sprint Book index — start here)
│   ├── README.md                     (numbering convention, file structure, detail status)
│   ├── sprint_1/
│   │   ├── sprint_1_1.md
│   │   ├── sprint_1_2.md
│   │   └── ...
│   ├── sprint_2/
│   └── ...                          (one subdirectory per Level, e.g. sprint_6/; one file per sprint inside: spec + Sprint Completion Report — corrected 2026-08-16, Sprint 6.22: sprint IDs are `<Level>.<SequentialIndex>`, file names `sprint_<level>_<index>.md`, one subdirectory per Level, not the flat `sprint_0_N.md` naming shown here previously and retired since Sprint 1.1, see backlog/technical_debt.md item 4)
├── changelog/                       (one entry per released version, e.g. 0.1.0.md)
├── tds/                             (Technical Design docs — one per sprint's Step 4 plan, where the plan is non-trivial)
└── backlog/                         (tracked technical debt and deferred/future work)
```

End of Part 5.
