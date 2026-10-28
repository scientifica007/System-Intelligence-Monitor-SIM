# Changelog — SIM

## 0.1.0a2 — 28/10/2026 (Alpha)

- Read true Linux distro name/version from `/etc/os-release` and expose readable GPU driver inventory, thermal readings and power-supply types.
- `sim doctor --memory-modules`: opt-in SMBIOS module inventory with explicit privilege; only size, type, slot, bank and speed are reported. Never export serial numbers.
- `sim show temperatures --json`: most recent recorded temperature readings with availability and degrees Celsius.
- `sim start --process-every N` (default 5): system-wide metrics retain normal cadence, detailed process metrics run every N samples. A CPU threshold of 75% schedules additional process detail on the next sample, not retroactively.
- `sim start --max-session-mib N` (default 128): terminal `size_limit` state prevents unbounded growth; session data are not automatically deleted. Final sample may slightly exceed limit.
- `processes_sampled` and `process_interval_ms` are additive JSONL fields. An empty processes list with `processes_sampled=false` does **not** mean no processes.
- `sim top` finds latest detailed sample while `sim show` continues to access latest system sample. Legacy 0.1.0a1 sessions remain readable.
- Automated unit and integration tests added or amended; FT-003 field validation pending.

**Not included:** long-running systemd --user daemon, SQLite, log rotation/compression, GPU per-process utilization, accurate watts per app, GTK Desktop. Stable release not declared.
