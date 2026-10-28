# FT-003 — Ubuntu 24.04.5 Alpha-2 field trial

**Status: executed; 1,137 matching JSONL records verified.** Functional PASS with a sampling-interval defect: 14 gaps >3s, maximum 23.902s. [FT-003 final report](FT003_FINAL.md). Test system: Intel Core i3 M370 (2 physical / 4 logical), 2×4 GB DDR3 RAM, Intel `8086:0046` GPU driver `i915`. Keep existing FT-001 and FT-002 data intact.

## Steps

1. Ensure old recorder is stopped: `.venv/bin/sim status`, then `.venv/bin/sim stop` if recording.
2. `git pull --ff-only`, then `.venv/bin/python -m pip install -e .`.
3. Check: `.venv/bin/sim --version` must report `SIM 0.1.0a2`.
4. Save diagnostics: `.venv/bin/sim doctor --json > ~/sim-ft003-doctor.json`.
5. Start: `.venv/bin/sim start --interval 2 --process-every 5 --process-limit 300 --max-session-mib 128 --label "FT-003 30 min" --json`.
6. Use Brave normally for **30 minutes**, noting approximate times of demanding activities. Review with `.venv/bin/sim status --json`, `.venv/bin/sim show temperatures --json` and `.venv/bin/sim top --sort cpu --limit 15`.
7. Stop: `.venv/bin/sim stop --json`. Obtain ID with `.venv/bin/sim sessions list --json`.
8. Export: `.venv/bin/sim export ACTUAL_SESSION_ID --format jsonl --output ~/sim-ft003.jsonl`. **Replace** ACTUAL_SESSION_ID with the real identifier; it is not a literal string.

## Data acceptance
- Time windows: expect approximately 900 samples in 30 min at a 2-second cadence. Count valid JSONL records and interruptions.
- Size: compare MB per hour against FT-001 (4.91 MB / 4m16s ≈68.5 MB/h), without claiming an improvement before measuring.
- Temperature: recorded Celsius values if supported; `not_detected` otherwise.
- Process sampling: `processes_sampled=false` indicates detail intentionally skipped. Recent `top` may lag; compare timestamps.
- Overhead: evaluate CPU, RSS and write activity caused by SIM, ideally with a baseline run without SIM under similar conditions.
- `size_limit` is a successful safety stop, not evidence that the planned duration completed.
- Compare with FT-001 on data rate and correctness only; workloads are not controlled sufficiently to claim CPU causality.
- Do not publish raw process logs without inspecting private details.

## Subsequent test
After analyzing FT-003, conduct a 2-hour stability test with explicit storage limit and optional `--process-every 1` short-run comparison. Neither test has been completed yet.


## Field checkpoint: 28/10/2026

The user completed the 38m53s recording session, obtained 1,137 samples according to `sim stop`, and confirmed `sim show temperatures` and `sim top` during the run. Doctor JSON reports Ubuntu 24.04.5, i915 and accessible sensors. The first attached JSONL was checked independently and **belongs to FT-001** (129 records, earlier session ID), **not FT-003**. The program is not known to have exported an incorrect session; the wrong attachment was provided. See [FT-003 preliminary report](FT003_PRELIMINARY.md).

To export the correct session without overwriting a prior file:

```bash
cd ~/System-Intelligence-Monitor-SIM
.venv/bin/sim export 20261028T204716Z-9381b675 --format jsonl --output ~/sim-ft003-20261028.jsonl
wc -l ~/sim-ft003-20261028.jsonl
du -h ~/sim-ft003-20261028.jsonl
head -n 1 ~/sim-ft003-20261028.jsonl | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["session_id"])'
```

Expected session ID is `20261028T204716Z-9381b675`; the expected sample count is **1,137**, barring export anomalies that require investigation. The result must be shared privately, not committed as a public process log.


## Final validation — 28/10/2026

The correct file `sim-ft003-20261028.jsonl` was received and all **1,137** records match `20261028T204716Z-9381b675`. Export size **10,282,740 bytes**; actual data rate **15.871 MB/hour**, versus **69.004 MB/hour** in FT-001, a **77.00% reduction**. All samples have four temperature readings; recorded Core 0 maximum **68°C**, Core 2 maximum **65°C**. The most severe sample interval was **23.902 seconds**, with 14 intervals over 3 seconds. This prevents an unconditional timing PASS. The earlier wrong-file warning is now historical and resolved. Refer to [FT003_FINAL.md](FT003_FINAL.md) and [FT003_METRICS.json](FT003_METRICS.json) for authoritative results; do not rerun the export unnecessarily.
