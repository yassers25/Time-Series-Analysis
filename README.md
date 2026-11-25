# CDSL time series project

## Data

Place the scripts next to your existing `data/` folder. It contains 35 monthly
folders, from `202304` to `202602`:

```text
data/202304/
data/202305/
...
data/202601/
data/202602/
```

Each month contains daily `log-backup-*` folders and access-log files.
`DATA_DIR` points to the parent `data/` folder. Keep `START_DATE = None`

and `END_DATE = None` to process the full archive.

## Run

Python 3.10 or newer. From this directory, on Windows:

```powershell
python prepare_data.py
python plot_demo.py
```

## Output

- `outputs/months.csv`: inventory of the 35 expected folders, including absent folders.
- `outputs/audit.csv`: files, record counts, event dates, and copied snapshots.
- `outputs/hourly.csv` and `outputs/daily.csv`: aggregated request counts.
- `outputs/parse_errors.csv`: rejected lines, created only when parsing fails.
- `02_daily_traffic.png/.pdf`: full daily history.
- `01_hourly_traffic.png/.pdf`: recent hourly detail, controlled by `MAX_PLOT_DAYS`.

Figures are also written to `outputs/`. Monthly traffic summaries must use
event dates; `months.csv` describes the source folders.

Data: [CDSL Website Access Logs](https://github.com/cdsl-research/website-access-logs-public).
