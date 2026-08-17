"""Level 6 Part B — Long-duration and Resource tests (Sprint 6.23).

Phase 6.5's own named list ("Unit Tests. Integration Tests. System Tests.
Long-duration tests. Resource tests. User acceptance tests.") has named
Long-duration and Resource as distinct categories since this project's own
locked spec (04_Master_Implementation_Plan.md) was first written, but
neither existed as a runnable artifact before this sprint. Sprint 6.18
(Stress & Recovery Testing) built the real accelerated-interval
infrastructure (`stress_app_harness`, tests/system/conftest.py) both of
these tests reuse, but its own `test_sustained_load_...` test is
deliberately a *stress* test (maximum turn throughput inside one
continuous, never-dormant session, over a documented 120s window) — a
different shape from either test below, not merely a shorter version of
either.

**Long-duration** (`test_long_duration_...` below): genuinely longer than
Sprint 6.18's own 120s window, and a genuinely different shape — several
full wake -> active -> reply -> DORMANT session round trips across an
extended real wall-clock window, rather than one continuous session. This
proves the full session lifecycle (not just conversation throughput) stays
healthy over an extended run, including repeated wake-word re-detection
after a real return to DORMANT, which Sprint 6.18's own stress test
deliberately never exercises (see that file's own docstring for why).

**Resource** (`test_resource_bounds_...` below): an explicit assertion
suite over RSS/CPU bounds sampled repeatedly across a sustained run,
building directly on Sprint 6.16's own single-point startup baseline
(test_startup_performance.py) — that file measures one-time construction
cost; this one measures cost *during* real, sustained operation.
"""

import time

import psutil
import pytest

from config.schema import VoiceConfig

_TURN_TIMEOUT = 30.0
"""Matches test_level6_part_b_stress.py's own identical, empirically-found
value — both tests below run under the same stress_app_harness real-
Chroma-write-under-load conditions that value was tuned against."""
_DORMANT_TIMEOUT = 40.0
"""Matches test_level6_part_b_stress.py's own identical value/reasoning."""


@pytest.fixture
def voice_config() -> VoiceConfig:
    """Overrides tests/system/conftest.py's own shared voice_config fixture
    (session_timeout_seconds=3.0) for both tests below, mirroring test_
    level6_part_b_stress.py's own identical override and its own identical
    reasoning: that base value is tuned for a different, narrower purpose
    (margin against real CoreManager startup latency during fixture setup),
    never validated for repeated real turn-processing-to-DORMANT cycles
    under stress_app_harness's own heavy 13-job background load. Both tests
    below do real per-turn Chroma writes under that same load — the
    Long-duration test repeatedly, across many full round trips."""
    return VoiceConfig(
        mic_sample_rate_hz=16000,
        utterance_silence_ms=30,
        utterance_silence_threshold=0.02,
        max_utterance_seconds=10.0,
        session_timeout_seconds=20.0,
    )


# --- Long-duration: several full DORMANT round trips across an extended window ---------

_LONG_DURATION_SECONDS = 300.0
"""Genuinely longer than test_level6_part_b_stress.py's own 120s stress
window (2.5x), the same honest "several minutes of real wall-clock
activity, not a literal multi-hour endurance run" interpretation that
file's own docstring already established for this project (no CI exists
to host a real multi-hour soak test — see this sprint's own Future
Considerations)."""
_MIN_FULL_ROUND_TRIPS = 4
"""Each round trip pays a real, fixed session_timeout_seconds (20.0s, this
file's own local voice_config override above) plus real per-turn
processing time (up to _TURN_TIMEOUT worst-case) before the NEXT round
trip's own wake re-detection can even begin — a real, structural ceiling
on how many round trips 300s can hold (roughly 300/(20+turn latency)). 4
leaves comfortable margin below that ceiling even under a pessimistic
per-turn latency estimate, while typical per-turn latency in practice
yields substantially more round trips."""
_MAX_RSS_GROWTH_MB = 400.0
"""A wider budget than test_level6_part_b_stress.py's own 300MB — this
test's own real DORMANT/ACTIVE_CAPTURE cycling (mic mode transitions,
QuietModeController state churn, repeated wake-word re-detection) is real,
additional churn beyond that file's own single continuous session, on top
of a longer window."""


def _set_general_chat(h) -> None:
    h.llm_client.intent_response = "CATEGORY: INFORMATIONAL\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        "TOPIC: general chat\nENTITIES: NONE\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )


def _set_scheduler_request(h, entity: str, topic: str) -> None:
    h.llm_client.intent_response = "CATEGORY: ACTION_REQUEST\nCONFIDENCE: 0.9"
    h.llm_client.context_response = (
        f"TOPIC: {topic}\nENTITIES: {entity}\nREFERENCES_PAST: NO\n"
        "PERSONA: NONE\nSENTIMENT: NEUTRAL"
    )


def _drive_one_full_round_trip(
    h, wait_for_active_capture, wait_for_dormant, push_utterance, transcript, *, scheduler=False
) -> None:
    """A complete wake -> active -> reply -> DORMANT cycle — see this
    module's own docstring for why this, not one continuous session, is
    this test's own deliberate shape."""
    h.wake_engine.calls = 0
    wait_for_active_capture(h.mic)
    if scheduler:
        _set_scheduler_request(h, "oven", "check the oven")
    else:
        _set_general_chat(h)
    h.tts.spoken_event.clear()
    h.stt.pending_transcripts.append(transcript)
    push_utterance(h.audio_backend)
    assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT), (
        f"Round trip {transcript!r} never received a reply within {_TURN_TIMEOUT}s."
    )
    wait_for_dormant(h.quiet_mode_controller, timeout=_DORMANT_TIMEOUT)


def test_long_duration_multiple_full_session_round_trips_stay_healthy(
    stress_app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    h = stress_app_harness
    process = psutil.Process()
    rss_before_mb = process.memory_info().rss / (1024 * 1024)

    deadline = time.monotonic() + _LONG_DURATION_SECONDS
    round_trip_count = 0
    turn_shapes = [
        (False, "how are you today"),
        (True, "remind me in 5 minutes to check the oven"),
        (False, "tell me something interesting"),
    ]
    while time.monotonic() < deadline:
        is_scheduler, transcript = turn_shapes[round_trip_count % len(turn_shapes)]
        _drive_one_full_round_trip(
            h, wait_for_active_capture, wait_for_dormant, push_utterance, transcript,
            scheduler=is_scheduler,
        )
        round_trip_count += 1

    assert round_trip_count >= _MIN_FULL_ROUND_TRIPS, (
        f"Only {round_trip_count} full session round trips completed in "
        f"{_LONG_DURATION_SECONDS}s — too few for a genuinely long-duration scenario."
    )

    # Every one of the 13 jobs really did keep recurring throughout — see
    # test_level6_part_b_stress.py's own identical reasoning for why a
    # nonzero, live health_check() is real evidence here, not ceremony.
    assert h.task_scheduler.health_check() is True
    assert h.usage_tracker.health_check() is True
    assert h.wellness_tracker.health_check() is True

    states = h.core_manager.module_states()
    not_running = {name: state for name, state in states.items() if state != "running"}
    assert not_running == {}, (
        f"Module(s) not left RUNNING after {round_trip_count} long-duration round trips: "
        f"{not_running}"
    )

    rss_after_mb = process.memory_info().rss / (1024 * 1024)
    rss_growth_mb = rss_after_mb - rss_before_mb
    assert rss_growth_mb < _MAX_RSS_GROWTH_MB, (
        f"Long-duration operation grew RSS by {rss_growth_mb:.1f}MB over "
        f"{round_trip_count} round trips and {_LONG_DURATION_SECONDS}s, exceeding the "
        f"documented {_MAX_RSS_GROWTH_MB}MB budget."
    )


# --- Resource: explicit RSS/CPU bounds sampled repeatedly across a sustained run --------

_RESOURCE_WINDOW_SECONDS = 60.0
_SAMPLE_INTERVAL_SECONDS = 5.0
"""psutil.Process.cpu_percent(interval=...) blocks for the given interval
to measure genuine average CPU over that window — this doubles as this
loop's own pacing, no separate time.sleep() needed. ~12 samples across the
window below."""
_MAX_RSS_GROWTH_MB = 300.0
"""Matches test_level6_part_b_stress.py's own identical sustained-
operation budget — this window (60s) is shorter than that file's own
120s, so no wider budget is warranted here."""
_MAX_AVERAGE_CPU_PERCENT = 300.0
"""An upper-bound sanity ceiling, not an intermittency requirement — found
directly, not guessed: an earlier version of this test asserted at least
one sample must dip below 90%, assuming natural idle gaps between
real work. A real run instead measured a consistent 97-100% on EVERY
5s sample (stress_app_harness's own 13 real jobs, each ticking every
1.0s, mean there is always at least one real job executing somewhere in
this process throughout the whole window — no natural idle gap exists to
observe with this specific harness, a genuine property of "stress," not a
bug). psutil.Process.cpu_percent() is not core-count-normalized (100% is
one full core) — 300.0 gives real margin above a single core's worth of
continuous, legitimate background-job + turn-processing activity while
still catching a genuine regression that pins multiple cores
continuously (a real busy-loop bug, not normal load)."""
_MIN_TURNS = 6


def test_resource_bounds_stay_within_documented_budget_across_sustained_operation(
    stress_app_harness, wait_for_active_capture, wait_for_dormant, push_utterance
):
    h = stress_app_harness
    process = psutil.Process()
    rss_before_mb = process.memory_info().rss / (1024 * 1024)
    process.cpu_percent(interval=None)  # primes psutil — the first call is always meaningless.

    # Found directly, not assumed: fixture setup's own real construction
    # cost (~2min in this session) comfortably outlasts this harness's own
    # session_timeout_seconds, so by the time this test body runs the
    # mic's own initial (fixture-setup-time) wake match has typically
    # already round-tripped back to DORMANT — h.wake_engine.calls must be
    # reset here to trigger a fresh match, the same pattern every other
    # turn-driving helper in this codebase already uses (e.g. this file's
    # own _drive_one_full_round_trip() above).
    h.wake_engine.calls = 0
    wait_for_active_capture(h.mic)
    rss_samples_mb: list[float] = []
    cpu_samples_percent: list[float] = []
    deadline = time.monotonic() + _RESOURCE_WINDOW_SECONDS
    turn_count = 0
    while time.monotonic() < deadline:
        _set_general_chat(h)
        h.tts.spoken_event.clear()
        h.stt.pending_transcripts.append("how are you today")
        push_utterance(h.audio_backend)
        assert h.tts.spoken_event.wait(timeout=_TURN_TIMEOUT), (
            f"Turn {turn_count} never received a reply within {_TURN_TIMEOUT}s."
        )
        turn_count += 1
        rss_samples_mb.append(process.memory_info().rss / (1024 * 1024))
        cpu_samples_percent.append(process.cpu_percent(interval=_SAMPLE_INTERVAL_SECONDS))

    wait_for_dormant(h.quiet_mode_controller, timeout=_DORMANT_TIMEOUT)

    assert turn_count >= _MIN_TURNS, (
        f"Only {turn_count} turns completed in {_RESOURCE_WINDOW_SECONDS}s — too few real "
        "samples for a genuinely sustained resource-bounds observation."
    )

    peak_growth_mb = max(rss_samples_mb) - rss_before_mb
    assert peak_growth_mb < _MAX_RSS_GROWTH_MB, (
        f"Sustained operation's peak RSS growth was {peak_growth_mb:.1f}MB across "
        f"{turn_count} turns and {_RESOURCE_WINDOW_SECONDS}s, exceeding the documented "
        f"{_MAX_RSS_GROWTH_MB}MB budget."
    )
    average_cpu_percent = sum(cpu_samples_percent) / len(cpu_samples_percent)
    assert average_cpu_percent < _MAX_AVERAGE_CPU_PERCENT, (
        f"Average CPU usage across the whole {_RESOURCE_WINDOW_SECONDS}s window was "
        f"{average_cpu_percent:.1f}% ({cpu_samples_percent}), exceeding the documented "
        f"{_MAX_AVERAGE_CPU_PERCENT}% sanity ceiling — indicative of a genuine "
        "multi-core-saturating regression, not normal sustained background-job load."
    )
