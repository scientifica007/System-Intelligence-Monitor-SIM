# SIM v0.1.0a2 — Implementation report

**Date:** 28/10/2026. **State:** alpha-2 candidate; FT-003 completed and its 1,137-record JSONL has been independently verified. Functionality and storage-rate reduction pass; irregular sampling gaps remain and require correction.

## Completed functionality
1. `doctor`: true OS identity, GPU device IDs + detected driver, temperature sensor descriptions, inventory of power-supply interfaces, and explicit capability status.
2. Optional `doctor --memory-modules`: privilege required, restricted SMBIOS fields only; no automatic elevation and no serial numbers.
3. `Collector`: system counters per interval, process details at configurable N, temperature readings in sample, and separate process interval metadata.
4. `Recorder`: configurable session-size guard, terminal `size_limit` state and event log; no automatic deletion of files.
5. `CLI`: `sim show temperatures`, `--process-every`, `--max-session-mib`; `top` selects most recent detailed sample.
6. Existing JSONL fields/units remain; added fields are optional to preserve interoperability with v0.1.0a1.

## Risks / remaining scope
- Detached subprocess continues as backend. **No implemented systemd user service or guarantee after logout.**
- Hard session size cap is not compression, rotation, SQLite or a complete retention engine.
- Detail every N samples can miss short-lived processes. CPU spike monitoring schedules detail on the next cycle.
- GPU load and process watt estimation remain not implemented. Temperature readings depend on actual hardware.
- `top` can lag behind current system counters. GPU inventory does not imply GPU utilization support.
- No field results for Alpha 2 yet; FT-003 must compare data size, CPU overhead, sensor availability and sample timing against FT-001.

[Field test FT-003](FT003_PROTOCOL.md) · [Changelog](../CHANGELOG.md).


## FT-003 initial field checkpoint (28/10/2026)

The device reported a stopped session lasting 38m53s with 1,137 samples (session `20261028T204716Z-9381b675`). Temperature display and process top responded during recording. `sim-ft003-doctor.json` validated system identification and i915 sensor inventory. The received file named `sim-scond-test.jsonl` is instead the prior FT-001 export (129 records, session `20261028T194549Z-479a6b04`); therefore no FT-003 data-rate or interval PASS claim has been made. [FT-003 checkpoint and pending deliverables](FT003_PRELIMINARY.md).


## FT-003 final evaluation (28/10/2026)

A subsequent upload supplied the correct 1,137-record JSONL for session `20261028T204716Z-9381b675`, superseding the prior missing-file blocker. All records parse correctly. Size 10,282,740 bytes over 2,332.400 seconds (15.871 MB/hour), a 77% reduction versus FT-001 at 69.004 MB/hour. All samples contain four accessible temperature readings; peak Core 0 temperature 68°C. However, 19 timing gaps exceeded 2.5 seconds, of which 14 exceeded 3 seconds, the longest lasting 23.902 seconds. **Functional PASS / sampling-timing defect OPEN / no stable release approval.** The workload difference does not permit causal claims about CPU overhead. See [complete FT-003 report](FT003_FINAL.md) and [aggregate machine-readable metrics](FT003_METRICS.json).
