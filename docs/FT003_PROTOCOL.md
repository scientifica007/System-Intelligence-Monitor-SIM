# FT-003 — Ubuntu 24.04.5 Alpha-2 field trial

**Status: not executed.** Test system: Intel Core i3 M370 (2 physical / 4 logical), 2×4 GB DDR3 RAM, Intel `8086:0046` GPU driver `i915`. Keep existing FT-001 and FT-002 data intact.

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
