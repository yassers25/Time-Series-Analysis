"""Read extracted CDSL access logs, audit each file, and build hourly/daily CSVs."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
SERVICES = ("wp", "doktor")
START_DATE = None  # Inclusive YYYY-MM-DD in JST.
END_DATE = None  # Exclusive YYYY-MM-DD in JST.

UTC = timezone.utc
JST = timezone(timedelta(hours=9), name="JST")
ARCHIVE_MONTHS = list(pd.period_range("2023-04", "2026-02", freq="M").strftime("%Y%m"))
MONTH_FOLDER_RE = re.compile(r"\d{4}(?:0[1-9]|1[0-2])")
MONTHS = {name: number for number, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
)}
FILE_RE = re.compile(r"^access\.(.+)\.log(?:\.\d+)?$")
TIME_RE = re.compile(r"^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})$")
HTTP_RE = re.compile(
    r'^\S+\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<request>(?:[^"\\]|\\.)*)"\s+(?P<status>\d{3})\s+(?P<size>\d+|-)\s+'
    r'"(?:[^"\\]|\\.)*"\s+"(?P<ua>(?:[^"\\]|\\.)*)"'
    r'(?:\s+"(?:[^"\\]|\\.)*")*\s*$'
)
REQUEST_RE = re.compile(r"^\S+\s+\S+\s+HTTP/\d+(?:\.\d+)?$")
BOT_RE = re.compile(r"bot|crawl|spider", re.IGNORECASE)
STATUS_COLUMNS = [f"status_{number}xx" for number in range(1, 6)] + ["status_other"]
COUNT_COLUMNS = ["requests", "monitor_requests", "other_requests", "declared_bot_requests",
                 *STATUS_COLUMNS, "bytes_sent", "missing_byte_values", "nonstandard_requests"]
AUDIT_COUNTS = ["raw_lines", "blank_lines", "parsed_records", "parse_errors", "in_window_records"]
AUDIT_DATES = ["first_event_utc", "last_event_utc", "first_event_local", "last_event_local"]


def parse_time(value: str) -> datetime:
    """Parse the explicit UTC offset without relying on English system locales."""
    match = TIME_RE.fullmatch(value)
    if match is None:
        raise ValueError("Unrecognized event timestamp")
    day, month, year, hour, minute, second, sign, offset_hour, offset_minute = match.groups()
    if month.title() not in MONTHS or int(offset_hour) > 23 or int(offset_minute) > 59:
        raise ValueError("Invalid month or UTC offset")
    offset = (60 * int(offset_hour) + int(offset_minute)) * (1 if sign == "+" else -1)
    return datetime(int(year), MONTHS[month.title()], int(day), int(hour), int(minute),
                    int(second), tzinfo=timezone(timedelta(minutes=offset))).astimezone(UTC)


def _boundary(value: str | None) -> datetime | None:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=JST).astimezone(UTC) if value else None


def _new_hour() -> dict:
    return {**dict.fromkeys(COUNT_COLUMNS, 0), "clients": set()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fractions(row: dict) -> None:
    for name, numerator in (("monitor", "monitor_requests"), ("status_4xx", "status_4xx"),
                            ("status_5xx", "status_5xx")):
        row[f"{name}_fraction"] = row[numerator] / row["requests"] if row["requests"] > 0 else np.nan


def _folder_month(path: Path, data_dir: Path) -> str:
    parts = (data_dir.name, *path.relative_to(data_dir).parts[:-1])
    return next((part for part in reversed(parts) if MONTH_FOLDER_RE.fullmatch(part)), "")


def _write_months(output_dir: Path, folders: dict, file_counts: Counter, audit: pd.DataFrame) -> None:
    rows = []
    for month in sorted(set(ARCHIVE_MONTHS) | set(folders)):
        present = month in folders
        selected = audit.loc[audit["folder_month"] == month]
        unique = selected.loc[selected["duplicate_of"] == ""]
        first = selected["first_event_local"].replace("", np.nan).dropna()
        last = selected["last_event_local"].replace("", np.nan).dropna()
        rows.append({"month": month, "expected_archive_month": month in ARCHIVE_MONTHS,
                     "folder_present": present, "folders": " | ".join(folders.get(month, [])),
                     "file_count": file_counts[month] if present else pd.NA,
                     "selected_access_files": len(selected) if present else pd.NA,
                     "unique_selected_files": len(unique) if present else pd.NA,
                     "parsed_records": int(unique["parsed_records"].sum()) if present else pd.NA,
                     "records_used": int(selected["records_used"].sum()) if present else pd.NA,
                     "first_event_local": first.min() if len(first) else "",
                     "last_event_local": last.max() if len(last) else ""})
    pd.DataFrame(rows).to_csv(output_dir / "months.csv", index=False)


def prepare(data_dir: Path = DATA_DIR, output_dir: Path = OUTPUT_DIR,
            services: tuple[str, ...] = SERVICES, start_date: str | None = START_DATE,
            end_date: str | None = END_DATE) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Scan every selected-service file; filter records by event time, not folder name.

    Identical files count once per service. Repeated lines remain requests.
    Without an explicit start date, each service starts on its first event day.
    Empty hours are unknown; daily totals require a record in every hour.
    """
    data_dir, output_dir = Path(data_dir).resolve(), Path(output_dir).resolve()
    if not data_dir.is_dir():
        raise NotADirectoryError(f"Expected an extracted data folder: {data_dir}")
    services = tuple(dict.fromkeys(services))
    if not services:
        raise ValueError("Select at least one service")
    start, end = _boundary(start_date), _boundary(end_date)
    if start and end and start >= end:
        raise ValueError("END_DATE must follow START_DATE")
    files, folders, file_counts = [], defaultdict(list), Counter()
    if MONTH_FOLDER_RE.fullmatch(data_dir.name):
        folders[data_dir.name].append(".")
    for path in data_dir.rglob("*"):
        if path.is_dir():
            if MONTH_FOLDER_RE.fullmatch(path.name):
                folders[path.name].append(path.relative_to(data_dir).as_posix())
            continue
        if not path.is_file():
            continue
        file_counts[_folder_month(path, data_dir)] += 1
        match = FILE_RE.fullmatch(path.name)
        if match and match[1] in services:
            files.append((path, match[1]))
    found = sum(month in folders for month in ARCHIVE_MONTHS)
    print(f"Archive month folders found: {found}/{len(ARCHIVE_MONTHS)} expected (202304 to 202602).")
    if found < len(ARCHIVE_MONTHS):
        print("Processing available input only; months.csv identifies absent folders.")
    audit_dir = output_dir / "audit"
    tables_dir = output_dir / "tables"
    audit_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    if not files:
        empty = pd.DataFrame(columns=["folder_month", "duplicate_of", "first_event_local",
                                      "last_event_local", "parsed_records", "records_used"])
        _write_months(audit_dir, folders, file_counts, empty)
        raise FileNotFoundError(f"No selected-service access logs found under {data_dir}")
    hours, seen_files, audit_rows = defaultdict(_new_hour), {}, []
    errors_path = audit_dir / "parse_errors.csv"
    failures = 0
    with errors_path.open("w", encoding="utf-8", newline="") as error_file:
        errors = csv.DictWriter(error_file, fieldnames=["file", "line_number", "reason", "raw_line"])
        errors.writeheader()
        for path, service in sorted(files):
            relative = path.relative_to(data_dir).as_posix()
            digest = _sha256(path)
            row = {"file": relative, "folder_month": _folder_month(path, data_dir),
                   "service": service, "size_bytes": path.stat().st_size,
                   "sha256": digest, "duplicate_of": "", "records_used": 0,
                   "backup_label": next((part for part in path.parts if part.startswith("log-backup-")), ""),
                   **dict.fromkeys(AUDIT_COUNTS, 0), **dict.fromkeys(AUDIT_DATES, "")}
            key = (service, digest)
            if key in seen_files:
                original = seen_files[key]
                row.update({name: original[name] for name in AUDIT_COUNTS + AUDIT_DATES})
                row["duplicate_of"] = original["file"]
                audit_rows.append(row)
                continue
            seen_files[key] = row
            first = last = None
            with path.open("rb") as source:
                for line_number, raw in enumerate(source, 1):
                    row["raw_lines"] += 1
                    if not raw.strip():
                        row["blank_lines"] += 1
                        continue
                    try:
                        line = raw.decode("utf-8").rstrip("\r\n")
                        match = HTTP_RE.fullmatch(line)
                        if match is None:
                            raise ValueError("Unrecognized HTTP access-log envelope")
                        timestamp = parse_time(match["time"])
                    except (ValueError, UnicodeDecodeError) as exc:
                        row["parse_errors"] += 1
                        failures += 1
                        errors.writerow({"file": relative, "line_number": line_number, "reason": str(exc),
                                         "raw_line": raw.decode("utf-8", errors="replace").rstrip("\r\n")})
                        continue
                    row["parsed_records"] += 1
                    first = timestamp if first is None else min(first, timestamp)
                    last = timestamp if last is None else max(last, timestamp)
                    if (start and timestamp < start) or (end and timestamp >= end):
                        continue
                    row["in_window_records"] += 1
                    row["records_used"] += 1
                    hour = hours[(service, timestamp.replace(minute=0, second=0, microsecond=0))]
                    agent = match["ua"].casefold()
                    monitor = "uptimerobot" in agent or "elastic-heartbeat" in agent
                    hour["requests"] += 1
                    hour["monitor_requests"] += int(monitor)
                    hour["other_requests"] += int(not monitor)
                    hour["declared_bot_requests"] += int(bool(BOT_RE.search(agent)))
                    hour["nonstandard_requests"] += int(REQUEST_RE.fullmatch(match["request"]) is None)
                    hour["clients"].add(line.split(None, 1)[0])
                    code = int(match["status"]) // 100
                    hour[f"status_{code}xx" if 1 <= code <= 5 else "status_other"] += 1
                    if match["size"] == "-":
                        hour["missing_byte_values"] += 1
                    else:
                        hour["bytes_sent"] += int(match["size"])
            if first is not None:
                row.update(first_event_utc=first.isoformat(), last_event_utc=last.isoformat(),
                           first_event_local=first.astimezone(JST).isoformat(), last_event_local=last.astimezone(JST).isoformat())
            audit_rows.append(row)
    if not failures:
        errors_path.unlink()
    audit = pd.DataFrame(audit_rows)
    audit.to_csv(audit_dir / "audit.csv", index=False)
    _write_months(audit_dir, folders, file_counts, audit)
    if not hours:
        raise ValueError("No records matched. audit.csv was written; hourly/daily CSVs were not regenerated.")

    first_hour, last_hour = min(key[1] for key in hours), max(key[1] for key in hours)
    grid_start = start or first_hour.astimezone(JST).replace(hour=0).astimezone(UTC)
    grid_end = end or (last_hour.astimezone(JST).replace(hour=0) + timedelta(days=1)).astimezone(UTC)
    hourly_rows = []
    for service in services:
        service_times = [time for name, time in hours if name == service]
        service_start = grid_start
        if start is None and service_times:
            service_start = min(service_times).astimezone(JST).replace(hour=0).astimezone(UTC)
        grid = pd.date_range(service_start, grid_end, freq="h", inclusive="left")
        for timestamp in grid:
            values = hours.get((service, timestamp.to_pydatetime()))
            present = values is not None
            row = {"service": service, "time_utc": timestamp.isoformat(),
                   "time_local": timestamp.tz_convert(JST).isoformat(), "has_events": present,
                   "bin_status": "events_present" if present else "unknown"}
            row.update({name: values[name] if present else np.nan for name in COUNT_COLUMNS})
            row["unique_clients"] = len(values["clients"]) if present else np.nan
            if present and values["missing_byte_values"]:
                row["bytes_sent"] = np.nan
            _fractions(row)
            hourly_rows.append(row)
    hourly = pd.DataFrame(hourly_rows)
    hourly.to_csv(tables_dir / "hourly.csv", index=False)
    daily_rows = []
    for (service, day), group in hourly.groupby(["service", hourly["time_local"].str[:10]], sort=False):
        observed = int(group["has_events"].sum())
        row = {"service": service, "date_local": day, "hours_with_events": observed,
               "expected_hours": len(group), "unknown_hours": len(group) - observed,
               "requests_recorded": int(group["requests"].sum())}
        row.update({name: group[name].sum(min_count=len(group)) for name in COUNT_COLUMNS})
        _fractions(row)
        daily_rows.append(row)
    daily = pd.DataFrame(daily_rows)
    daily.to_csv(tables_dir / "daily.csv", index=False)
    unique_files = audit["duplicate_of"].eq("")
    print(f"Selected records: {int(audit['records_used'].sum()):,}; hourly rows: {len(hourly):,}")
    print(f"Files audited: {len(audit)}; exact duplicate files skipped: {int((~unique_files).sum())}; parse failures: {failures}")
    print(f"Event-day window: {grid_start.astimezone(JST).date()} to {grid_end.astimezone(JST).date()} (exclusive), JST")
    print("Hours without records are written as missing values.")
    return audit, hourly, daily


if __name__ == "__main__":
    prepare()
