"""Level 6 Part B — Full Test Suite Pass (Sprint 6.23) formal Acceptance
Pass, closing Level 6 Part B — and, joined with Sprint 6.15's own Part A
freeze, all of Level 6. Mirrors Sprint 2.14/3.14/4.13/4.20/5.16/5.26/6.15's
own identical closing role for their own Levels/Parts.

One continuous scripted scenario (`test_level6_part_b_full_acceptance_
scenario` below) through the real, complete Level 1-6 (Part A + Part B)
`CoreManager` graph. Covers, in order:

1. A fresh startup timed and RSS-measured against Sprint 6.16's own
   documented baseline (test_startup_performance.py's 110s/1000MB budget,
   reused directly rather than inventing a second, parallel threshold).
2. A sustained multi-job window with a real induced-CRITICAL
   `ResourceMonitor` reading (Sprint 6.19's own technique, reused directly
   from test_level6_part_b_resource_protection.py), confirming only the
   `resource_sensitive=True` jobs pause while a real, non-sensitive job
   keeps recurring throughout.
3. A real secret round trip through `SecretStore` (Sprint 6.20), confirmed
   never touching plaintext `local.yaml` — a real `ConfigLoader.save()`
   call against a disposable, tmp_path-scoped file, never this project's
   own real `config/local.yaml`.
4. A real `KnowledgeGraphStore`/`UsageStore` purge cycle plus a real
   `InternetConfig.enabled=False` block (Sprint 6.21), both confirmed for
   real through a live conversation turn rather than merely re-asserted at
   the unit level.

**A real, disclosed finding from writing this file's own Step 2, found
directly, not assumed**: `stress_app_harness` (tests/system/conftest.py,
Sprint 6.18) constructs its own `TaskScheduler` with `resource_monitor=
None` (`resource_aware_scheduler` defaults to `False` there and is never
overridden by that fixture) — a deliberate Sprint 6.19 design choice, per
that fixture's own docstring, to avoid re-opening Sprint 6.18's own
already-verified stress-test behavior. `TaskScheduler.add_job()` decides
whether to wrap a `resource_sensitive=True` job at all ONCE, at
registration time, based on `self._resource_monitor is not None`
(scheduler/task_scheduler.py) — so a job registered through
`stress_app_harness` can never actually be resource-gated, regardless of
what `ResourceMonitor.sample()` later returns. An earlier version of this
test used `stress_app_harness` for this step and its own resource-pause
assertion passed for the wrong reason once (a stale, pre-construction
monkeypatch target that was never actually invoked) and then failed for
the *right* reason once fixed (a real `4 == 0` mismatch) — this second
failure is what surfaced the harness-choice problem itself, not a bug in
`scheduler/task_scheduler.py`. This step now uses `fast_resource_
protection_app_harness` (Sprint 6.19's own dedicated, already-verified
resource-aware fixture) instead — the same real, complete Level 1-6 Part
A+B graph, with `resource_monitor` genuinely wired into `TaskScheduler`.
"""

import time
from datetime import UTC, datetime, timedelta

import keyring
import psutil

from analytics.usage_model import AppFocusSample
from analytics.usage_tracker import UsageTracker
from config.loader import ConfigLoader
from core.resource_monitor import ResourceSnapshot
from knowledge.knowledge_model import Entity, EntityType
from scheduler.reminder_engine import ReminderEngine
from security.secret_store import _SERVICE_NAME, SecretStore

_TURN_TIMEOUT = 30.0
"""Matches test_level6_part_b_stress.py's own identical, empirically-found
value — this scenario drives real turns under real background-job load,
the same condition that value was tuned against."""
_DORMANT_TIMEOUT = 40.0
_OBSERVATION_WINDOW_SECONDS = 2.0
"""Matches test_level6_part_b_resource_protection.py's own identical
value/reasoning — fast_resource_protection_app_harness's own 0.3s job
interval gives ~6-7 ticks across this window, comfortably enough for a
real, non-flaky "stayed at zero / kept climbing" observation."""
_MAX_STARTUP_SECONDS = 110.0
_MAX_STARTUP_RSS_GROWTH_MB = 1000.0
"""Both reused directly from test_startup_performance.py (Sprint 6.16) —
this step's own Objectives text is explicit that the baseline is Sprint
6.16's own documented one, not a new, second threshold."""

_DISPOSABLE_SECRET_NAME = "jarminei_acceptance_test_probe_secret"


def _real_keyring_backend_available() -> bool:
    """Mirrors tests/unit/security/test_secret_store.py's own identical
    probe — this scenario's own secret-round-trip step degrades to a
    softer, still-meaningful assertion (get/set never raise, no plaintext
    written) rather than failing outright on an environment with no usable
    OS credential backend, the same "advisory, not fatal" posture this
    project's real-hardware-dependent real-verification tiers already use
    elsewhere."""
    try:
        keyring.set_password(_SERVICE_NAME, _DISPOSABLE_SECRET_NAME, "probe")
        keyring.delete_password(_SERVICE_NAME, _DISPOSABLE_SECRET_NAME)
        return True
    except Exception:
        return False


def test_level6_part_b_full_acceptance_scenario(
    request, wait_for_active_capture, wait_for_dormant, push_utterance, tmp_path, monkeypatch
):
    # --- Step 2's own tick-counting wrappers are installed at the CLASS
    # level BEFORE the harness is even constructed below — found directly,
    # not assumed: UsageTracker.start()/ReminderEngine.register() each
    # capture their own tick method as a bound method the instant
    # TaskScheduler.add_job() is called, during the harness's own fixture
    # setup. Patching the class AFTER that setup already ran has no effect
    # on the job APScheduler already holds a reference to — the identical
    # finding tests/system/test_level6_part_b_resource_protection.py's own
    # job_tick_counts fixture already documents ("Must be requested BEFORE
    # ... in a test's own parameter list"), applied here via request.
    # getfixturevalue() instead of fixture-parameter-ordering since this
    # test also needs to time the harness's own construction (Step 1). -----
    tick_counts = {"usage_sample": 0, "reminder_poll": 0}
    original_usage_tick = UsageTracker._on_tick
    original_reminder_poll = ReminderEngine._poll_due_items

    def _counting_usage_tick(self):
        tick_counts["usage_sample"] += 1
        return original_usage_tick(self)

    def _counting_reminder_poll(self):
        tick_counts["reminder_poll"] += 1
        return original_reminder_poll(self)

    monkeypatch.setattr(UsageTracker, "_on_tick", _counting_usage_tick)
    monkeypatch.setattr(ReminderEngine, "_poll_due_items", _counting_reminder_poll)

    # --- Step 1: a fresh, real, complete-graph startup, timed/RSS-measured
    # against Sprint 6.16's own documented baseline. request.getfixturevalue()
    # mirrors test_startup_performance.py's own identical technique for
    # bracketing fixture setup with a plain timer, chosen for the identical
    # reason: core_manager.startup() happens deep inside the harness's own
    # fixture setup, before any caplog context in this test body could take
    # effect. fast_resource_protection_app_harness (not stress_app_harness
    # — see this module's own docstring for why) is still the real,
    # complete Level 1-6 Part A+B graph; only the fixture's own
    # SchedulerConfig/AnalyticsConfig interval overrides differ, which do
    # not affect real construction/startup cost. ------------------------------
    process = psutil.Process()
    rss_before_startup_mb = process.memory_info().rss / (1024 * 1024)
    started_at = time.perf_counter()
    h = request.getfixturevalue("fast_resource_protection_app_harness")
    startup_elapsed_seconds = time.perf_counter() - started_at
    rss_after_startup_mb = process.memory_info().rss / (1024 * 1024)

    assert startup_elapsed_seconds < _MAX_STARTUP_SECONDS, (
        f"Real, complete Level 1-6 (Part A + Part B) graph startup took "
        f"{startup_elapsed_seconds:.2f}s, exceeding Sprint 6.16's own documented "
        f"{_MAX_STARTUP_SECONDS}s budget."
    )
    assert (rss_after_startup_mb - rss_before_startup_mb) < _MAX_STARTUP_RSS_GROWTH_MB, (
        f"Real, complete-graph startup grew RSS by "
        f"{rss_after_startup_mb - rss_before_startup_mb:.1f}MB, exceeding Sprint 6.16's own "
        f"documented {_MAX_STARTUP_RSS_GROWTH_MB}MB budget."
    )

    # --- Step 2: a sustained multi-job window with a real induced-CRITICAL
    # ResourceMonitor reading, confirming a resource_sensitive=True job
    # (usage_tracker_sample) genuinely pauses while a non-sensitive job
    # (reminder_engine's own poll) keeps recurring — the identical
    # technique test_level6_part_b_resource_protection.py already
    # established, now re-confirmed against a full acceptance scenario
    # rather than a narrower, dedicated file. -----------------------------
    def _critical_snapshot() -> ResourceSnapshot:
        return ResourceSnapshot(
            cpu_percent=99.0,
            ram_percent=50.0,
            disk_percent=50.0,
            battery_percent=None,
            timestamp=datetime.now(UTC),
        )

    monkeypatch.setattr(h.resource_monitor, "sample", _critical_snapshot)
    tick_counts["usage_sample"] = 0
    tick_counts["reminder_poll"] = 0

    time.sleep(_OBSERVATION_WINDOW_SECONDS)

    assert tick_counts["usage_sample"] == 0, (
        "usage_tracker_sample (resource_sensitive=True) ticked at least once while a "
        "real CRITICAL ResourceMonitor reading held during this sprint's own full "
        "acceptance scenario."
    )
    assert tick_counts["reminder_poll"] >= 3, (
        "reminder_engine_poll (not resource_sensitive) failed to keep recurring "
        f"normally during the same CRITICAL window — only "
        f"{tick_counts['reminder_poll']} tick(s)."
    )

    def _normal_snapshot() -> ResourceSnapshot:
        return ResourceSnapshot(
            cpu_percent=10.0,
            ram_percent=30.0,
            disk_percent=40.0,
            battery_percent=None,
            timestamp=datetime.now(UTC),
        )

    monkeypatch.setattr(h.resource_monitor, "sample", _normal_snapshot)

    # --- Step 3: a real secret round trip through SecretStore, confirmed
    # never touching plaintext local.yaml — a disposable, tmp_path-scoped
    # target file, never this project's own real config/local.yaml. --------
    secret_store = SecretStore()
    secret_value = "acceptance-test-secret-value-never-in-yaml"
    if _real_keyring_backend_available():
        try:
            secret_store.set_secret(_DISPOSABLE_SECRET_NAME, secret_value)
            assert secret_store.get_secret(_DISPOSABLE_SECRET_NAME) == secret_value
        finally:
            try:
                keyring.delete_password(_SERVICE_NAME, _DISPOSABLE_SECRET_NAME)
            except Exception:
                pass
    else:
        secret_store.set_secret(_DISPOSABLE_SECRET_NAME, secret_value)  # must not raise
        secret_store.get_secret(_DISPOSABLE_SECRET_NAME)  # must not raise

    config = h.core_manager.config()
    config.internet.search_api_key = secret_value
    local_target = tmp_path / "acceptance_local.yaml"
    loader = ConfigLoader(local_path=local_target, secret_store=secret_store)
    loader.save(config, path=local_target)
    saved_text = local_target.read_text(encoding="utf-8")
    assert secret_value not in saved_text, (
        "A real secret value leaked into a saved local.yaml — ConfigLoader.save() must "
        "force internet.search_api_key/tavily_api_key to null unconditionally (Sprint 6.20)."
    )
    assert "search_api_key: null" in saved_text

    # --- Step 4a: a real KnowledgeGraphStore/UsageStore purge cycle. -------
    now = datetime.now(UTC)
    stale_entity = Entity(
        entity_id="acceptance-stale-project",
        entity_type=EntityType.PROJECT,
        name="A long-dormant project",
        description="Referenced once, long ago.",
        created_at=now - timedelta(days=800),
        last_referenced_at=now - timedelta(days=800),
    )
    h.knowledge_graph_store.save_entity(stale_entity)
    assert h.knowledge_graph_store.get_entity(stale_entity.entity_id) is not None
    kg_removed = h.knowledge_graph_store.purge_older_than()
    assert kg_removed >= 1
    assert h.knowledge_graph_store.get_entity(stale_entity.entity_id) is None

    h.usage_store.record_sample(
        AppFocusSample(
            process_name="acceptance-stale-app.exe",
            window_title="A long-stale focus sample",
            sampled_at=now - timedelta(days=800),
        )
    )
    usage_removed = h.usage_store.purge_older_than()
    assert usage_removed >= 1

    # --- Step 4b: a real InternetConfig.enabled=False block, confirmed
    # through a live conversation turn — no outbound SearchProvider call
    # happens at all, matching voice/pipeline.py's own _handle_internet_
    # agent_turn() docstring ("not merely that the reply changes while a
    # request still goes out"). ----------------------------------------------
    h.internet_config.enabled = False
    h.wake_engine.calls = 0
    wait_for_active_capture(h.mic)
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: JARMINEI project news\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )
    h.tts.spoken_event.clear()
    calls_before = len(h.fake_search_provider.calls)
    h.stt.pending_transcripts.append("search the internet for the latest JARMINEI project news")
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT), (
        "The internet-agent opt-out turn never received a reply."
    )
    reply_text, _ = h.tts.speak_calls[-1]
    assert reply_text == "Internet research is currently turned off."
    assert len(h.fake_search_provider.calls) == calls_before, (
        "A real outbound SearchProvider call happened despite InternetConfig.enabled=False."
    )
    wait_for_dormant(h.quiet_mode_controller, timeout=_DORMANT_TIMEOUT)

    # No unhandled exception anywhere in the whole registered graph across
    # this entire multi-part scenario — matches test_level6_part_b_stress.py's
    # own identical, exhaustive module_states() check.
    states = h.core_manager.module_states()
    not_running = {name: state for name, state in states.items() if state != "running"}
    assert not_running == {}, f"Module(s) not left RUNNING after the full scenario: {not_running}"
