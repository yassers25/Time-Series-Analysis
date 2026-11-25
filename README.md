# CDSL time series project

## Folder structure

```text
cdsl_demo/
  data/                          Original logs, ignored by Git
    202304/ ... 202602/           Monthly archive folders
  scripts/                       Runnable Python scripts
    prepare_data.py              Parse, deduplicate and aggregate logs
    audit_quality.py             Check consistency, dates and missing hours
    plot_traffic.py              Plot hourly and daily traffic
  notebooks/
    data_exploration.ipynb        Interactive exploration
    missing_observations.ipynb    Investigate gaps using coverage and file dates
  outputs/
    tables/                      Hourly and daily time series
    audit/                       File audit, quality report and supporting tables
    figures/                     PNG and PDF plots
  .gitignore
  README.md
```

Keep executable code in `scripts/`, exploration in `notebooks/`, and generated
results in the appropriate `outputs/` subfolder. Future modelling and evaluation
work should follow these same locations.

Keep the original monthly folders directly under `data/`. Each contains daily
`log-backup-*` folders and access-log files. In `scripts/prepare_data.py`, leave
`START_DATE` and `END_DATE` as `None` to process the full archive.

## Run

Use Python 3.10 or newer with NumPy, pandas and Matplotlib installed.
From the project root, run these commands in order:

```powershell
python scripts/prepare_data.py
python scripts/audit_quality.py
python scripts/plot_traffic.py
```

To check existing CSVs without regenerating them, run only
`python scripts/audit_quality.py`. It uses the standard library and exits with a
nonzero status if consistency checks fail. It does not change the source logs
or prepared time series.

The notebook's first cell supports a working directory of either the project
root or `notebooks/`.
It builds JST-indexed `hourly_counts` and `daily_counts` for `wp`, counts missing
periods, and displays daily and recent hourly plots. Change `service` to
`'doktor'` to examine that service. Unknown counts remain missing; no imputation
is applied. Detailed consistency checks belong in `scripts/audit_quality.py`.
The first notebook also answers the five Step 1 archive and preparation questions,
with timestamp samples, duplicate and parsing evidence, and the cleaning policy.
Its written findings describe wp; changing `service` changes the series cells only.

Use `notebooks/missing_observations.ipynb` to plot missing hours, inspect a
selected gap against the file audit, and compare coverage between services.
Start with the longest wp gap; change `gap_number` to inspect another interval.

## Output

- `outputs/tables/hourly.csv` and `daily.csv`: aggregated counts and coverage indicators.
- `outputs/audit/months.csv`: inventory of the 35 expected folders, including absent folders.
- `outputs/audit/audit.csv`: files, record counts, event dates, and duplicate references.
- `outputs/audit/parse_errors.csv`: rejected lines, created only when parsing fails.
- `outputs/audit/quality_report.md`: readable quality findings.
- `outputs/audit/quality_summary.csv`: service-level quality totals.
- `outputs/audit/quality_checks.csv`: failed consistency checks; header only if all pass.
- `outputs/audit/missing_intervals.csv`: consecutive hours without recorded events.
- `outputs/audit/date_mismatches.csv`: files with events outside their folder month.
- `outputs/audit/overlapping_ranges.csv`: unique files with overlapping timestamp ranges.
- `outputs/figures/02_daily_traffic.png` and `.pdf`: full daily history.
- `outputs/figures/01_hourly_traffic.png` and `.pdf`: recent hourly detail, controlled by `MAX_PLOT_DAYS`.

Hours without records remain unknown rather than zero; daily totals require
records in every hour. Time bins use JST (UTC+09:00). Monthly traffic summaries
must use event dates; `months.csv` describes the source folders.

Data: [CDSL Website Access Logs](https://github.com/cdsl-research/website-access-logs-public).
