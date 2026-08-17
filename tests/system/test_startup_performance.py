"""Startup/resource performance baseline (Sprint 6.16, Level 6 Part B —
Startup & Caching Optimization). No test anywhere in this codebase asserted
a startup-time or resource-usage bound before this sprint — every one of
backlog/technical_debt.md's own "host-load wait_for_dormant-class flake"
entries is indirect evidence startup/resource cost was being watched only
informally (via flaky-test symptoms), never measured directly.

**A real, disclosed scope note**: app_harness (tests/system/conftest.py)
registers every ManagedModule without a tier/lazy argument, so — per
core/manager.py's own register_module() default — everything in it runs as
ServiceTier.ALWAYS_LOADED, non-lazy, exactly like every other tests/system/
file already relies on for determinism. This test therefore measures the
real, complete Level 1-6 Part A graph's own eager construction+registration+
startup() cost end to end (every real class genuinely built and started,
fakes only at the mic/wake-engine/STT/TTS/Ollama boundary) — a strictly
LARGER number than real production's own Tier-A-only synchronous slice
(ui/app.py's run_app(), Runtime Phase 4), since Tier A is a subset of what
this test starts. That makes the threshold below a conservative, honest
upper-bound regression guard, not a literal reproduction of the tiered
production startup experience — the tiering MECHANISM itself (Tier A
finishes before Tier B/C even begins, WARM modules are skipped by
startup_tier(ALWAYS_LOADED)) is already proven correct at the unit level
(tests/unit/core/test_manager.py's own
test_startup_tier_only_starts_modules_registered_in_that_tier() and
neighbors); this file adds the one thing that suite doesn't: real numbers
against the real, complete graph.

Threshold philosophy matches this project's own already-established
tolerance for real-machine variability (the same reasoning behind the
long-documented host-load wait_for_dormant flake class) — generous, not
CI-grade tight, since no CI exists to tune against. A failure here should
get the identical "standalone re-run, confirm real regression vs.
transient host load" investigation every other flake in this project's own
history has already received (see e.g. sprint_6/sprint_6_14.md's Sprint
Completion Report) — this file deliberately does not invent a new live
host-load-detection skip mechanism no other test in this codebase uses.
"""

import time

import psutil

# Empirically ~50-55s wall-clock on this project's own development
# machine, measured directly (three real runs, this exact test file,
# before picking a threshold — not guessed) — dominated by the real
# chromadb.PersistentClient(...) connect() (including the onnxruntime
# embedding model), real SQLite connects across a dozen+ stores, and Qt
# widget construction for the presentation layer. ~2x the observed
# wall-clock ceiling and a wide, absolute RSS budget, matching this
# project's own generous-threshold philosophy.
_MAX_STARTUP_SECONDS = 110.0
_MAX_RSS_GROWTH_MB = 1000.0


def test_real_complete_system_startup_completes_within_a_generous_budget(request):
    """Times app_harness's own real construction+registration+startup()
    (see this module's own docstring for why that's the honest, complete-
    graph number to measure) via request.getfixturevalue() — the standard
    pytest mechanism for resolving a fixture on demand, chosen specifically
    so this test can bracket the fixture's own setup with a plain
    time.perf_counter()/psutil measurement instead of depending on
    core/manager.py's own internal timing-log record's emission order
    relative to caplog, which conftest.py's own construction never
    guarantees. app_harness's own normal teardown (core_manager.shutdown())
    still runs automatically once this test ends — getfixturevalue()
    registers with pytest's ordinary fixture finalizer stack, exactly as if
    app_harness were a plain parameter."""
    process = psutil.Process()
    rss_before_bytes = process.memory_info().rss

    started_at = time.perf_counter()
    request.getfixturevalue("app_harness")
    elapsed_seconds = time.perf_counter() - started_at

    rss_after_bytes = process.memory_info().rss
    rss_growth_mb = (rss_after_bytes - rss_before_bytes) / (1024 * 1024)

    assert elapsed_seconds < _MAX_STARTUP_SECONDS, (
        f"Real, complete-graph startup took {elapsed_seconds:.2f}s, "
        f"exceeding the documented {_MAX_STARTUP_SECONDS}s budget — investigate "
        "for a genuine regression before assuming transient host load "
        "(standalone re-run first, per this project's own established "
        "flake-investigation discipline)."
    )
    assert rss_growth_mb < _MAX_RSS_GROWTH_MB, (
        f"Real, complete-graph startup grew RSS by {rss_growth_mb:.1f}MB, "
        f"exceeding the documented {_MAX_RSS_GROWTH_MB}MB budget."
    )
