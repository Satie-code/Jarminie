# JARMINEI User Acceptance Test Checklist

Phase 6.5's own locked spec ([04_Master_Implementation_Plan.md](04_Master_Implementation_Plan.md)) names "User acceptance tests" alongside Unit/Integration/System/Long-duration/Resource tests as one of six required test categories. Every prior Level-freeze sprint since Sprint 2.14 has disclosed a real, outstanding manual-verification gap in its own completion report — a genuine, honest limitation of an automated suite, never glossed over — but until now no single document collected them. This checklist is that document: every disclosed item, named once, cross-referenced back to the sprint that first found it, in the order a person would actually reasonably perform them on the real target machine.

**This document is a checklist to run, not a report of what's already been verified.** Every box below is unchecked because no session to date has had a human available to speak, listen, watch a screen, or supply a real external credential — see each sprint's own completion report (linked below) for the exact, honest disclosure. `v1.0` is gated on this checklist being run to completion by a human, plus explicit user authorization — see [sprint_6_23.md](sprint_book/sprint_6/sprint_6_23.md)'s own Integration Considerations.

**How to use this document**: work through each section in order (later sections build on earlier ones being functional). Check a box only after actually performing that step on the real target machine and observing the described outcome. If a step fails, stop and file it as a real bug — do not check the box and continue.

---

## 0. Before you start

- [ ] Running on the actual target laptop (Windows), not a VM or CI-style headless environment — several items below depend on real audio hardware, a real display, and real OS-level services (Windows Credential Manager) that a headless environment either lacks or fakes.
- [ ] `python main.py` launches cleanly with no unhandled exception, and the desktop shell/status panel appears.
- [ ] A working microphone and speakers/headphones are connected and selected as the OS default input/output device.

---

## 1. Level 2 — Communication (wake word, speech, voice reply)

**Disclosed at:** [sprint_2_14.md](sprint_book/sprint_2/sprint_2_14.md) — "the one criterion that cannot be satisfied by any automated test in this Sprint Book."

- [ ] Say the wake phrase out loud. JARMINEI visibly/audibly enters listening mode.
- [ ] Speak a simple question or request. JARMINEI transcribes it correctly (or close enough that the reply makes sense) and speaks back a real, audible reply through the real TTS voice.
- [ ] The full round trip (wake word → your speech → spoken reply) completes without a crash, a silent hang, or a garbled/absent voice response.

---

## 2. Level 3 — Intelligence (memory, decision-making)

**Disclosed at:** [sprint_3_14.md](sprint_book/sprint_3/sprint_3_14.md) — explicitly states Level 3 has **no** equivalent irreducible manual step (Ollama is text-in/text-out and fully scriptable); the opt-in real-model tier below was already executed against a real Ollama instance during that sprint.

- [ ] (Optional, opt-in) `ollama pull llama3` (or set `JARMINEI_TEST_OLLAMA_MODEL` to a model you've already pulled), then run `pytest tests/system/test_level3_real_model_verification.py -m real_model`. Confirms real intent/context classification and real ChromaDB embedding ranking against your own local Ollama instance, not just the fake used everywhere else.
- [ ] Say something and follow it up a few turns later with a reference to it (e.g. "remember what I just told you about X?"). JARMINEI's reply shows it actually recalled the earlier content, not just acknowledged the new turn in isolation.

---

## 3. Level 4 Part A — Device Control & Workflow Automation

**Disclosed at:** [sprint_4_13.md](sprint_book/sprint_4/sprint_4_13.md) — "was NOT performed in this session," disposable-scope-only.

- [ ] Ask JARMINEI to launch a real, harmless application (e.g. Notepad) by voice. It actually opens.
- [ ] Ask JARMINEI to close that application by voice. It actually closes.
- [ ] Ask JARMINEI to perform a file operation confined to a scratch/throwaway folder you don't mind it touching (e.g. create a text file). The file actually appears with the expected content.
- [ ] Ask JARMINEI to perform a window operation (e.g. minimize/move a window). It actually happens.
- [ ] Ask for a two-step workflow where one step requires confirmation (e.g. "open Notepad, then close it" if your build's confirmation policy gates the second step). You are actually prompted for confirmation, and your voice reply is correctly honored (both accept and, separately, deny/timeout paths).

---

## 4. Level 4 Part B — Scheduler & Internet Agent

**Disclosed at:** [sprint_4_20.md](sprint_book/sprint_4/sprint_4_20.md) — two real gaps, one behavioral and one environmental.

- [ ] Ask a real research question out loud (e.g. "what's the latest news on \[some real, current topic\]?"). JARMINEI speaks back a sensible, cited answer — not "internet research is currently turned off" (confirm `internet.enabled` is `true` in your local config first) and not a canned/garbled non-answer.
- [ ] Set a reminder for roughly a minute in the future by voice, then wait without talking to JARMINEI. It proactively speaks the reminder aloud, unprompted, at approximately the right time, while the system is idle.
- [ ] (Optional, opt-in, requires both a real search API key AND a real reachable Ollama instance) Set `JARMINEI_INTERNET_SEARCH_API_KEY` to a real key, ensure Ollama is running with the configured model pulled, then run `pytest tests/system/test_level4_part_b_real_verification.py -m "real_model and real_search_api"`. Confirms a real search query against the live provider and a real summarization pass over real results.

---

## 5. Level 5 Part A — Emotional Intelligence & Presentation Layer

**Disclosed at:** [sprint_5_16.md](sprint_book/sprint_5/sprint_5_16.md) — two real gaps, one visual/behavioral and one requiring a separate application.

- [ ] Watch the on-screen avatar (sphere/ring or VTube Studio model, depending on your configured renderer) during a conversation. Its animation is smooth, not stuttering or frozen.
- [ ] Say something emotionally clear (happy, urgent, sad) and watch the avatar/presentation respond — its expression, color, or pacing visibly shifts in a way that plausibly matches what you said.
- [ ] Trigger a persona switch (e.g. explicitly ask to switch personas, if your build supports it). The on-screen transition actually plays, not an abrupt cut or a frozen frame.
- [ ] (Optional, requires VTube Studio installed and running separately, with a Live2D model loaded and its API server enabled under Settings → API) Run `pytest tests/system/test_level5_part_a_real_verification.py`. Confirms a real connect+authenticate handshake, a real parameter-injection round trip, and a real hotkey trigger against your live VTube Studio instance, rather than the fake WebSocket boundary every other test uses. The first run will show a VTube Studio "Allow plugin" popup — click Allow within the configured timeout, or the test skips with an actionable reason instead of failing.

---

## 6. Level 5 Part B — Companion Intelligence

**Disclosed at:** [sprint_5_26.md](sprint_book/sprint_5/sprint_5_26.md) — "was NOT performed this session."

- [ ] Stay away from the keyboard/mic long enough to cross your configured idle threshold. JARMINEI genuinely surfaces a wellness prompt (e.g. a break suggestion) through its normal voice/presentation channel — not silence, not a crash.
- [ ] Use the machine normally (a mix of real applications) for a while, then check whatever analytics/usage surface your build exposes (dashboard, a spoken summary, etc.). The reported usage data plausibly reflects what you actually did — the right application names, roughly the right durations.
- [ ] After a reasonable amount of normal use, ask JARMINEI for a recommendation (or wait for one to be proactively offered, if your build does that). The recommendation content actually makes sense given what you've been doing — not generic or nonsensical.

---

## 7. Level 6 Part A — Autonomous Intelligence & Cognitive Architecture

**Disclosed at:** [sprint_6_15.md](sprint_book/sprint_6/sprint_6_15.md) — "explicitly disclosed as not performed by this automated suite."

- [ ] Ask JARMINEI to help you plan something small (e.g. "help me plan a small project"). Its spoken proposal actually sounds natural — a plausible milestone/task breakdown, not stilted template filler.
- [ ] Accept the proposal, then ask "why did you suggest that?" as a genuine follow-up. The spoken explanation actually answers what you meant, referencing the real reasoning behind the suggestion — not a generic non-answer.
- [ ] Leave an overdue calendar item or similarly proactive-worthy condition in place, then go idle. A proactive announcement lands at a sensible moment (not mid-conversation, not immediately spamming one after another) and the content is genuinely relevant.

---

## 8. Level 6 Part B — Stabilization (new items, this Part)

**Disclosed at:** [sprint_6_23.md](sprint_book/sprint_6/sprint_6_23.md) (this sprint) — two new items this Part introduces that no prior Level named.

- [ ] **Real secret round trip through Windows Credential Manager.** Open Windows Credential Manager (Control Panel → Credential Manager → Windows Credentials) after JARMINEI has run at least once with a real `internet.search_api_key`/`tavily_api_key` or a VTube Studio auth token configured. Confirm a `jarminei`-service entry actually exists there (proving `SecretStore` really persisted it), and separately confirm `config/local.yaml` contains `search_api_key: null`/`tavily_api_key: null` (proving the secret never round-tripped to the plaintext file). This is automated at the unit/system level (`tests/unit/security/test_secret_store.py`, `test_level6_part_b_acceptance.py`'s own Step 3) against this exact machine's real backend, but a human eyeballing the real Credential Manager UI is the only way to confirm the entry is genuinely there and genuinely usable by a real person managing their own credentials, not merely round-tripping inside a test process.
- [ ] **A real, sustained multi-hour run, observed rather than simulated.** Every automated Long-duration/Resource test in this codebase (`tests/system/test_level6_part_b_long_duration_and_resource.py`) uses `stress_app_harness`'s own accelerated job intervals (1.0s, not the real, shipped defaults of 30s–86400s) over a bounded few-minutes window — an honest, disclosed substitute for a literal multi-hour endurance run, since this project has no CI/scheduled-runner environment to host one (see [sprint_6_18.md](sprint_book/sprint_6/sprint_6_18.md)'s and this sprint's own Future Considerations). Leave JARMINEI running normally, with its real, un-accelerated configured intervals, for several hours (ideally overnight) during normal use. Confirm afterward: no crash, no unbounded memory growth (compare RSS at start vs. end via Task Manager), and the app is still fully responsive to a wake word at the end.

---

## 9. Opt-in real-dependency test tiers (reference)

These are not separate manual steps — they're the automated opt-in tests already referenced above, collected here for convenience. Each is self-skipping (never failing) when its real dependency isn't available, and each is excluded from the default full-suite run via its own pytest marker.

| File | Marker(s) | Real dependency needed |
|---|---|---|
| `tests/system/test_level3_real_model_verification.py` | `real_model` | A real, reachable Ollama instance with the configured model pulled |
| `tests/system/test_level4_part_b_real_verification.py` | `real_model`, `real_search_api` | Both of the above, plus a real `JARMINEI_INTERNET_SEARCH_API_KEY` |
| `tests/system/test_level5_part_a_real_verification.py` | *(none — self-skips via a live socket check, not a marker; see backlog item 65)* | A real, locally-running VTube Studio instance with a Live2D model loaded |
| `tests/unit/internet/test_brave_search_provider.py::test_real_brave_search_returns_plausible_results_for_a_known_query` | `real_search_api` | A real `JARMINEI_INTERNET_SEARCH_API_KEY` |

Run all of them at once (each still self-skips independently if its own dependency is missing): `pytest tests/ -m "real_model or real_search_api"` plus `pytest tests/system/test_level5_part_a_real_verification.py` separately (unmarked).

---

## 10. Sign-off

- [ ] Every section above (1–8) has been run to completion on the real target machine, by a human, with every box checked or a real bug filed for anything that didn't check out.
- [ ] Section 9's opt-in tiers have been run at least once against real credentials/a real Ollama instance/a real VTube Studio instance (not merely confirmed to skip cleanly).
- [ ] The user has given explicit authorization to tag `v1.0`, per [sprint_6_23.md](sprint_book/sprint_6/sprint_6_23.md)'s own Integration Considerations (this checklist plus authorization are both required — neither alone is sufficient).

Run by: _______________  Date: _______________  Result: _______________
