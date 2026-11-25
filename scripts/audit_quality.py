"""Check prepared CSVs without dependencies or changing the source logs."""

import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


OUTPUT = Path(__file__).resolve().parents[1] / "outputs"


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def missing_runs(rows):
    """Return consecutive unknown hours, marking gaps at either series edge."""
    runs = []
    start = None
    for index, row in enumerate(rows):
        missing = row["has_events"].lower() == "false"
        if missing and start is None:
            start = index
        if start is not None and (not missing or index == len(rows) - 1):
            stop = index + 1 if missing else index
            runs.append({"service": rows[start]["service"],
                         "start_local": rows[start]["time_local"],
                         "end_local_exclusive": (datetime.fromisoformat(rows[stop - 1]["time_local"])
                                                 + timedelta(hours=1)).isoformat(),
                         "hours": stop - start,
                         "location": "boundary" if start == 0 or stop == len(rows) else "internal"})
            start = None
    return runs


def main(output=OUTPUT):
    audit_dir = output / "audit"
    audit = read_csv(audit_dir / "audit.csv")
    hourly = read_csv(output / "tables" / "hourly.csv")
    daily = read_csv(output / "tables" / "daily.csv")
    months = read_csv(audit_dir / "months.csv")
    output = audit_dir
    issues = []

    def check(condition, category, reference, detail):
        if not condition:
            issues.append(dict(category=category, reference=reference, detail=detail))

    check(bool(audit) and bool(hourly) and bool(daily), "input", "tables", "Empty input table")
    files = {row["file"]: row for row in audit}
    check(len(files) == len(audit), "audit", "file", "Repeated file paths")
    unique = [row for row in audit if not row["duplicate_of"]]
    duplicates = [row for row in audit if row["duplicate_of"]]
    seen = set()
    date_rows = []
    for row in audit:
        ref = row["file"]
        n = lambda name: int(row[name])
        check(n("raw_lines") == n("blank_lines") + n("parsed_records") + n("parse_errors"),
              "line_accounting", ref, "Raw lines do not equal blank + parsed + rejected")
        check(0 <= n("in_window_records") <= n("parsed_records"), "window", ref, "Invalid in-window count")
        check(n("records_used") == (0 if row["duplicate_of"] else n("in_window_records")),
              "records_used", ref, "Used count inconsistent with duplicate/window status")
        if row["duplicate_of"]:
            original = files.get(row["duplicate_of"])
            check(original is not None, "duplicate", ref, "Duplicate target absent")
            if original:
                check(not original["duplicate_of"] and
                      (row["service"], row["sha256"]) == (original["service"], original["sha256"]),
                      "duplicate", ref, "Duplicate target is not a matching unique file")
                for field in ("size_bytes", "raw_lines", "blank_lines", "parsed_records", "parse_errors",
                              "in_window_records", "first_event_utc", "last_event_utc",
                              "first_event_local", "last_event_local"):
                    check(row[field] == original[field], "duplicate", ref, f"Mismatch in {field}")
        else:
            key = row["service"], row["sha256"]
            check(key not in seen, "duplicate", ref, "Identical file counted more than once")
            seen.add(key)
        dates = [row[name] for name in ("first_event_utc", "last_event_utc", "first_event_local", "last_event_local")]
        check(all(dates) if n("parsed_records") else not any(dates), "date", ref, "Date availability disagrees with records")
        if all(dates):
            first_utc, last_utc, first, last = map(datetime.fromisoformat, dates)
            check(first_utc == first and last_utc == last, "date", ref, "UTC and local timestamps differ")
            check(first <= last, "date", ref, "First event after last event")
            check(first.utcoffset() == last.utcoffset() == timedelta(hours=9), "date", ref, "Local timezone is not JST")
            folder = row["folder_month"]
            if first.strftime("%Y%m") != folder or last.strftime("%Y%m") != folder:
                date_rows.append({name: row[name] for name in
                                  ("file", "service", "folder_month", "duplicate_of", "first_event_local", "last_event_local")})

    services = sorted({row["service"] for row in hourly} | {row["service"] for row in audit})
    hourly_by_service = {service: sorted((row for row in hourly if row["service"] == service),
                                        key=lambda row: row["time_utc"]) for service in services}
    daily_hours = defaultdict(list)
    gaps = []
    statuses = [f"status_{n}xx" for n in range(1, 6)] + ["status_other"]
    count_columns = ["requests", "monitor_requests", "other_requests", "declared_bot_requests",
                     *statuses, "bytes_sent", "missing_byte_values", "nonstandard_requests"]
    for service, rows in hourly_by_service.items():
        gaps.extend(missing_runs(rows))
        previous = None
        for row in rows:
            ref = f"{service} {row['time_local']}"
            time = datetime.fromisoformat(row["time_utc"])
            check(previous is None or time - previous == timedelta(hours=1), "hourly_grid", ref, "Repeated or skipped hour")
            previous = time
            check(time == datetime.fromisoformat(row["time_local"]), "date", ref, "Hourly UTC/local mismatch")
            present = row["has_events"].lower() == "true"
            check(row["has_events"].lower() in ("true", "false"), "hourly", ref, "Invalid has_events value")
            check(row["bin_status"] == ("events_present" if present else "unknown"), "hourly", ref, "Inconsistent bin status")
            if present:
                check(float(row["requests"]) > 0, "hourly", ref, "Observed hour has no requests")
                check(float(row["requests"]) == float(row["monitor_requests"]) + float(row["other_requests"]),
                      "traffic_balance", ref, "Monitoring + other differs from total")
                check(float(row["requests"]) == sum(float(row[name]) for name in statuses),
                      "status_balance", ref, "Status counts differ from total")
            else:
                check(all(row[name] == "" for name in count_columns), "missing", ref, "Unknown hour has counts")
            daily_hours[service, row["time_local"][:10]].append(row)
        used = sum(int(row["records_used"]) for row in audit if row["service"] == service)
        check(used == sum(float(row["requests"] or 0) for row in rows), "reconciliation", service,
              "Audit used records differ from hourly total")
    daily_keys = set()
    for row in daily:
        key = row["service"], row["date_local"]
        check(key not in daily_keys, "daily", str(key), "Repeated service/day")
        daily_keys.add(key)
        hours = daily_hours.get(key, [])
        observed = sum(hour["has_events"].lower() == "true" for hour in hours)
        check(int(row["expected_hours"]) == len(hours) == 24, "daily", str(key), "Not a complete 24-hour grid")
        check(int(row["hours_with_events"]) == observed and int(row["unknown_hours"]) == len(hours) - observed,
              "daily", str(key), "Coverage counts disagree with hourly data")
        check(float(row["requests_recorded"]) == sum(float(hour["requests"] or 0) for hour in hours),
              "daily", str(key), "Recorded total disagrees with hourly data")
        for name in count_columns:
            complete = len(hours) == 24 and all(hour[name] != "" for hour in hours)
            check((row[name] != "" and float(row[name]) == sum(float(hour[name]) for hour in hours))
                  if complete else row[name] == "", "daily", f"{key} {name}", "Daily aggregation mismatch")
    check(daily_keys == set(daily_hours), "daily", "coverage", "Daily/hourly service-day keys differ")

    summary = []
    overlaps = []
    for service in services:
        active = []
        for row in sorted((row for row in unique if row["service"] == service and row["first_event_local"]),
                          key=lambda row: row["first_event_local"]):
            active = [other for other in active if other["last_event_local"] >= row["first_event_local"]]
            for other in active:
                overlaps.append(dict(service=service, file_a=other["file"], file_b=row["file"],
                                     overlap_start=row["first_event_local"],
                                     overlap_end=min(other["last_event_local"], row["last_event_local"])))
            active.append(row)
    for service, rows in hourly_by_service.items():
        service_files = [row for row in unique if row["service"] == service]
        copies = [row for row in duplicates if row["service"] == service]
        service_days = [row for row in daily if row["service"] == service]
        service_gaps = [gap for gap in gaps if gap["service"] == service]
        missing = sum(int(gap["hours"]) for gap in service_gaps)
        summary.append(dict(service=service, unique_files=len(service_files), duplicate_files=len(copies),
                            records_used=sum(int(row["records_used"]) for row in service_files),
                            duplicate_parsed_records=sum(int(row["parsed_records"]) for row in copies),
                            parse_errors=sum(int(row["parse_errors"]) for row in service_files),
                            first_grid_hour=rows[0]["time_local"] if rows else "",
                            last_grid_hour=rows[-1]["time_local"] if rows else "",
                            total_hours=len(rows), unknown_hours=missing,
                            unknown_percent=round(100 * missing / len(rows), 2) if rows else "",
                            internal_unknown_hours=sum(gap["hours"] for gap in service_gaps if gap["location"] == "internal"),
                            complete_days=sum(int(row["unknown_hours"]) == 0 for row in service_days),
                            partial_days=sum(0 < int(row["unknown_hours"]) < 24 for row in service_days),
                            empty_days=sum(int(row["unknown_hours"]) == 24 for row in service_days)))
    write_csv(output / "quality_checks.csv", ["category", "reference", "detail"], issues)
    write_csv(output / "missing_intervals.csv", ["service", "start_local", "end_local_exclusive", "hours", "location"], gaps)
    write_csv(output / "date_mismatches.csv", ["file", "service", "folder_month", "duplicate_of", "first_event_local", "last_event_local"], date_rows)
    write_csv(output / "overlapping_ranges.csv", ["service", "file_a", "file_b", "overlap_start", "overlap_end"], overlaps)
    if summary:
        write_csv(output / "quality_summary.csv", list(summary[0]), summary)
    report = ["# Data quality audit", "", f"Consistency violations: {len(issues):,}.", "",
              f"Files: {len(audit):,}; unique: {len(unique):,}; exact duplicates excluded: {len(duplicates):,}.",
              f"Expected archive folders present: {sum(row['folder_present'].lower() == 'true' for row in months if row['expected_archive_month'].lower() == 'true')}/35.",
              f"Files with event endpoints outside the folder month: {len(date_rows):,} "
              f"({sum(not row['duplicate_of'] for row in date_rows):,} unique).",
              f"Unique file pairs with overlapping inclusive timestamp ranges: {len(overlaps):,}. "
              "A shared second does not establish duplicate requests.", ""]
    for row in summary:
        report.extend([f"## {row['service']}", "",
                       f"{row['records_used']:,} used requests; {row['parse_errors']:,} rejected lines in unique files.",
                       f"{row['duplicate_files']:,} duplicate files exclude {row['duplicate_parsed_records']:,} parsed records.",
                       f"Grid: {row['first_grid_hour']} to {row['last_grid_hour']} (inclusive).",
                       f"Unknown hours: {row['unknown_hours']:,}/{row['total_hours']:,} ({row['unknown_percent']}%); "
                       f"internal: {row['internal_unknown_hours']:,}.",
                       f"Days: {row['complete_days']:,} complete, {row['partial_days']:,} partial, {row['empty_days']:,} without events.", "",
                       "Longest unknown intervals (end exclusive):", ""])
        for gap in sorted((gap for gap in gaps if gap["service"] == row["service"]), key=lambda gap: gap["hours"], reverse=True)[:5]:
            report.append(f"- {gap['start_local']} to {gap['end_local_exclusive']}: {gap['hours']:,} hours ({gap['location']}).")
        report.append("")
    copies_by_target = defaultdict(list)
    for row in duplicates:
        copies_by_target[row["duplicate_of"]].append(row)
    report.extend(["## Duplicate groups", ""])
    for target, copies in sorted(copies_by_target.items(), key=lambda item: len(item[1]), reverse=True):
        original = files[target]
        report.append(f"- {original['service']}: {len(copies):,} copies of `{target}`; "
                      f"{int(original['parsed_records']):,} parsed records in the original, "
                      f"events {original['first_event_local']} to {original['last_event_local']}.")
    report.append("")
    report.extend(["## wp coverage corrections and December gap", "",
                   "The wp series starts on 2 April 2023, its first day with recorded events. "
                   "The former shared grid started on 29 March because a stale doktor snapshot contained events from that date. "
                   "Removing those four days removes 96 artificial unknown hours from wp, without removing any requests.", "",
                   "Both services have no records from 19 through 21 December 2025 (72 hours). "
                   "This gap lies in the intended test period. Its counts remain unknown; "
                   "no forecast error can be calculated against missing observations. "
                   "Test scores will require the number of observed and excluded dates to be reported. "
                   "Exact split dates and forecasting evaluation have not yet been implemented.", ""])
    report.extend(["## Service selection for this study", "",
                   "Use **wp as the main series** for exploratory analysis and forecasting. "
                   "Keep **doktor as a secondary comparison** over a usable period, mainly from March 2025 onward. "
                   "These names identify separate websites/services, not different log formats.", "",
                   "| Service | Purpose | Role in this study |",
                   "| --- | --- | --- |",
                   "| wp | Public WordPress website with the lab blog and research introduction pages | Main forecasting series |",
                   "| doktor | Academic paper search web service built using microservices | Secondary comparison |",
                   "| rudder | Internal lab introduction website protected by Google Account SSO | Excluded from the main forecasting study |", "",
                   "Service descriptions: [dataset documentation](https://github.com/cdsl-research/website-access-logs-public#services).", "",
                   "The audited wp series has a longer usable history, more requests and fewer unknown hours "
                   "than doktor over their respective exported date ranges (see the service totals above). "
                   "Much of doktor's early archive repeats the same 66-request log from 29 March 2023; "
                   "the next unique log begins on 8 March 2025. "
                   "The full-grid unknown-hour percentage therefore also reflects different periods of usable coverage.", "",
                   "Within wp, compare total requests, identified monitoring requests and other requests. "
                   "Other requests can include bots and scanners and should not be interpreted as human visitors.", "",
                   "The [published dataset statistics](https://github.com/cdsl-research/website-access-logs-public#dataset-statistics) "
                   "list only 478 rudder entries across 478 files, before deduplication. "
                   "Rudder has not been independently audited here and is not included in the prepared time series.", "",
                   "Select the final modelling period after accounting for wp's known gaps. "
                   "This recommendation selects a service; it does not establish the most accurate forecasting model.", "",
                   "## Interpretation and limits", "",
                   "Unknown hours mean no recorded requests, not confirmed zero traffic or confirmed outages. "
                   "Complete days mean records exist in all 24 hours; this does not prove complete logging within each hour.", "",
                   "Folder/event-month differences describe backup contents and are not automatically timestamp errors. "
                   "Only event endpoints are checked against folder months.", "",
                   "Exact-duplicate checks use existing audit hashes. Source files were not rehashed or reparsed. "
                   "Partially overlapping files are not deduplicated by the preparation script. "
                   "Repeated requests cannot safely be deleted merely because timestamps or lines match.", "",
                   "The local log files use Windows line endings (CRLF). Their byte sizes and SHA-256 hashes "
                   "therefore differ from the original LF files, while request counts are unchanged. "
                   "The audit describes the local copies.", "",
                   "See quality_checks.csv for failed consistency checks, missing_intervals.csv for all gaps, "
                   "date_mismatches.csv for folder/date differences, overlapping_ranges.csv for timestamp overlap candidates, "
                   "and quality_summary.csv for service totals.", ""])
    (output / "quality_report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return len(issues)


if __name__ == "__main__":
    raise SystemExit(bool(main()))
