# FT-003 — preliminary field checkpoint (awaiting matching JSONL)

**Date:** 28/10/2026  
**SIM version intended:** v0.1.0a2  
**Host:** Ubuntu 24.04.5 LTS, Intel Core i3 M370 (2 cores / 4 logical), 8 GB installed as 2 × 4 GB, Intel GPU `8086:0046` and driver `i915`.  
**Data provenance:** User-supplied CLI output, `sim-ft003-doctor.json`, and attached `sim-scond-test.jsonl`, verified by reading every JSONL line. Only aggregate / generic information is included in this public report; no raw process logs are published.

## Confirmed session / CLI outcomes

| Item | Observed | Status |
|---|---|---|
| Session ID from `status/stop/list` | `20261028T204716Z-9381b675` | CONFIRMED |
| Started (UTC) | 2026-10-28T20:47:16.436+00:00 | CONFIRMED |
| Stopped (UTC) | 2026-10-28T21:26:09.694+00:00 | CONFIRMED |
| Duration | 38 minutes 53.258 seconds | PASS for >30m wall clock |
| `sim stop` state | stopped | PASS |
| `sample_count` from manifest | 1,137 | REPORTED, awaits file verification |
| `process_every` | 5 | CONFIRMED |
| `max_session_mib` | 128 | CONFIRMED |
| `sim show temperatures --json` | Four readable readings | PASS for snapshot display |
| `sim top --sort cpu` | Populated list with process timestamps | PASS for snapshot display |
| FT-003 JSONL integrity / actual size | No matching export received | PENDING |
| FT-003 sample interval / distribution | No matching export received | PENDING |

`status` showed ongoing recording, and `stop` returned stopped with no reported `size_limit` state. This does not independently prove the timing or content of every one of the 1,137 samples without reading their actual JSONL.

## Doctor result — confirmed

- `distribution`: Ubuntu 24.04.5 LTS, `os_id=ubuntu`, `os_version=24.04`, codename `noble`.
- Kernel `7.0.0-38-generic`, x86_64, 2 physical / 4 logical cores.
- RAM visible to Linux: `8,110,960,640` bytes (~7.554 GiB); physical 2 × 4 GB modules previously confirmed via SMBIOS.
- Intel GPU `vendor_id=0x8086`, `device_id=0x0046` using `i915`.
- Power supply interface: `AC` of type `Mains`; no battery sensor is detected; this does not prove physical absence of a battery.
- Memory modules `not_collected` deliberately because privileged opt-in was not requested.
- `gpu_per_process`, `power_per_process`, `smart` remain `not_implemented`.

## Temperature snapshots

`sim-ft003-doctor.json` measured near session start: ACPI `acpitz_0` 51°C, `acpitz_1` 53°C, coretemp Core 0 46°C and Core 2 49°C. At a later CLI `sim show temperatures` snapshot (21:25:35.289 UTC), values were 51°C, 55°C, 47°C and 47°C respectively. Coretemp sensor metadata reported `high=80°C` and `critical=90°C`; these are hardware-reported thresholds, not a guarantee of a safe temperature throughout the session. No claim about maximum temperature over 38m53s can be made without the matching FT-003 recording.

## Point-in-time process snapshot

The user ran `sim top` showing the last detailed process sample at 21:25:27.363 UTC; the leading Brave process used 57.7% of **one logical CPU** (~14.4% of four logical CPUs), GNOME Shell 7.8% (~1.95% machine), and the Python recorder 1.1% (~0.275% machine) **in that sample only**. These are not session averages. The most recent temperature query timestamp was ~7.9 seconds later; the separation is expected with sparse process sampling and does not by itself show data loss.

## Data provenance discrepancy — blocking the final statistical report

The supplied file `sim-scond-test.jsonl` is exactly the first test's 4,907,245-byte / 129-line recording, and every JSONL sample bears **session ID `20261028T194549Z-479a6b04`** with timestamps from 19:45:49 to 19:50:05 UTC. That is FT-001, not FT-003. The filename is not authoritative; the embedded `session_id` is decisive. Do not compute FT-003 file size, mean CPU, temperature distribution, sparse process-sampling effectiveness, gap statistics or overhead from this file.

## Requested follow-up

```bash
cd ~/System-Intelligence-Monitor-SIM
.venv/bin/sim export 20261028T204716Z-9381b675 --format jsonl --output ~/sim-ft003-20261028.jsonl
wc -l ~/sim-ft003-20261028.jsonl
du -h ~/sim-ft003-20261028.jsonl
head -n 1 ~/sim-ft003-20261028.jsonl | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["session_id"])'
```

The sample count should be 1,137, and the printed ID must be `20261028T204716Z-9381b675`. If the export differs, retain the file and investigate before claiming success. Previous outputs remain untouched; the export command refuses overwrite.

**Provisional decision:** recorder startup/status/temperature display/process top/stop and session duration PASS based on CLI evidence; FT-003 statistical acceptance remains OPEN.
