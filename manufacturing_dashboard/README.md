# PSA Line Dashboard (manufacturing_dashboard)

This addon provides a real-time manufacturing quality control dashboard integrating VICI Vision, Ruhlamat Press, and Aumann Measurement. It ingests CSV files, computes pass/reject per station, aggregates per-part results, and exposes dashboards and station UIs.

## Install
1. Ensure this directory is in your addons path.
2. Update Apps and install "PSA Line Dashboard".

## Configure Machines
- Menu: Manufacturing Dashboard → Machine Configuration
- For each machine:
  - Set Machine Type
  - Set CSV File Path (full path)
  - Set Sync Interval (seconds)
  - Mark Active
  - Click "Sync Now" to test

A cron (see `data/cron_data.xml`) may call `sync_all_machines`. Each machine respects its own `sync_interval` seconds throttle.

## Models
- `manufacturing.machine.config`: orchestrates sync
- `manufacturing.vici.vision`: VICI measurements, tolerances, results
- `manufacturing.ruhlamat.press`: press measurements/results
- `manufacturing.aumann.measurement`: measurement/results
- `manufacturing.part.quality`: per-serial aggregation and QE override

## VICI CSV
- Multi-row header expected: names, then Nominal, Lower tol, Upper tol; data starts at row 7.
- Stored fields include metadata (operator, batch, measure), measurements (`l_*`, `runout_*`, `ang_diff_*`), per-measurement tolerances (`*_nominal/_tol_low/_tol_high`), `within_tolerance`, `result`, `rejection_reason`.

Manual import from shell:
```python
env['manufacturing.vici.vision'].browse().import_vici_csv(machine_id=<ID>, filename='vici_vision_data.csv')
```

## Notes
- Duplicates prevented per `(machine_id, serial_number)`
- `within_tolerance`: value in [nominal+low, nominal+high]
- CSV encoding: utf-8-sig

## Creditinals
Postgres password: asd@admin

login admin
pass asd@admin




