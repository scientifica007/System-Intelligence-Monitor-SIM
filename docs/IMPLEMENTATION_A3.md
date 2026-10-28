# SIM v0.1.0a3 — Execution and verification

**Date:** 28/10/2026. **Status:** Implemented candidate, locally tested, pending GitHub CI and FT-004 on the target HP device.

## Changed code
- `src/sim/recorder.py`: absolute monotonic scheduling; skips stale slots rather than generating catch-up samples. Records per-sample `timing` and emits `sampling_delay` / `schedule_overrun` events. Writes delay-event and skipped-deadline totals to manifest when recorder finishes. The 128 MiB size guard and user-controlled stop are unchanged.
- `src/sim/summary.py`: new streaming analysis module for previous a1/a2 sessions and a3 sessions. Uses constant memory with respect to sample count except for distinct sensor identifiers. No raw process command lines or paths in results; numeric means omit null.
- `src/sim/cli.py`: `sim summary SESSION_ID [--json]` works without a running recorder. Existing command paths retained.
- `src/sim/__init__.py` and `pyproject.toml`: 0.1.0a3.
- `tests/test_a3.py`: scheduler boundaries, legacy session compatibility, gap recognition, corruption/foreign ID handling and E2E recorder timing/summary. Older regression suite retained.

## Technical trade-offs
This release **instruments and characterizes** the 23.9s gap problem discovered in FT-003; it cannot promise to remove delays until the root cause is measured. `Collector.sample` is still called synchronously and slow I/O or OS scheduling can delay it. A first timing sample has null previous write time. The final sample's write-time can only appear in a next sample, so it may be absent from timing aggregates. Delay detection is based on monotonic timestamps when available; events are written separately from samples.

A three-second threshold is appropriate for a two-second cadence, but longer user-configured intervals use `max(3s, interval×1.5)` to avoid false alerts. The summary can read prior-schema sessions whose records lack the timing field. A2 data retained unchanged.

## Evidence and milestones
Local isolated Python tests passed, and the historical **1,137-record FT-003 file** was successfully summarized with 14 gaps over 3 seconds. The monotonic maximum differs slightly from the UTC maximum (time sources differ), which is correctly identified in the protocol. This does not substitute for a live FT-004 on the user's Ubuntu device.

[FT-004 protocol](FT004_PROTOCOL.md) · [FT-003 final report](FT003_FINAL.md) · [Issue #7](../issues/7).
