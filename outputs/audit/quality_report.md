# Data quality audit

Consistency violations: 0.

Files: 1,576; unique: 1,244; exact duplicates excluded: 332.
Expected archive folders present: 35/35.
Files with event endpoints outside the folder month: 374 (43 unique).
Unique file pairs with overlapping inclusive timestamp ranges: 5. A shared second does not establish duplicate requests.

## doktor

507,309 used requests; 0 rejected lines in unique files.
331 duplicate files exclude 21,846 parsed records.
Grid: 2023-03-29T00:00:00+09:00 to 2026-02-03T23:00:00+09:00 (inclusive).
Unknown hours: 18,017/25,032 (71.98%); internal: 18,016.
Days: 291 complete, 2 partial, 750 without events.

Longest unknown intervals (end exclusive):

- 2023-03-29T17:00:00+09:00 to 2025-03-08T08:00:00+09:00: 17,031 hours (internal).
- 2025-07-23T00:00:00+09:00 to 2025-08-28T00:00:00+09:00: 864 hours (internal).
- 2025-12-19T00:00:00+09:00 to 2025-12-22T00:00:00+09:00: 72 hours (internal).
- 2025-06-24T00:00:00+09:00 to 2025-06-25T00:00:00+09:00: 24 hours (internal).
- 2025-07-21T00:00:00+09:00 to 2025-07-22T00:00:00+09:00: 24 hours (internal).

## wp

4,779,893 used requests; 0 rejected lines in unique files.
1 duplicate files exclude 7,071 parsed records.
Grid: 2023-04-02T00:00:00+09:00 to 2026-02-03T23:00:00+09:00 (inclusive).
Unknown hours: 2,087/24,936 (8.37%); internal: 2,087.
Days: 952 complete, 1 partial, 86 without events.

Longest unknown intervals (end exclusive):

- 2025-07-23T00:00:00+09:00 to 2025-08-28T00:00:00+09:00: 864 hours (internal).
- 2024-12-07T00:00:00+09:00 to 2025-01-09T00:00:00+09:00: 792 hours (internal).
- 2023-04-07T00:00:00+09:00 to 2023-04-11T00:00:00+09:00: 96 hours (internal).
- 2024-11-01T00:00:00+09:00 to 2024-11-04T00:00:00+09:00: 72 hours (internal).
- 2025-12-19T00:00:00+09:00 to 2025-12-22T00:00:00+09:00: 72 hours (internal).

## Duplicate groups

- doktor: 331 copies of `202304/log-backup-20230403072346/access.doktor.log.1`; 66 parsed records in the original, events 2023-03-29T01:13:53+09:00 to 2023-03-29T16:27:38+09:00.
- wp: 1 copies of `202304/log-backup-20230403072346/access.wp.log.1`; 7,071 parsed records in the original, events 2023-04-02T00:00:44+09:00 to 2023-04-02T23:58:10+09:00.

## wp coverage corrections and December gap

The wp series starts on 2 April 2023, its first day with recorded events. The former shared grid started on 29 March because a stale doktor snapshot contained events from that date. Removing those four days removes 96 artificial unknown hours from wp, without removing any requests.

Both services have no records from 19 through 21 December 2025 (72 hours). This gap lies in the intended test period. Its counts remain unknown; no forecast error can be calculated against missing observations. Test scores will require the number of observed and excluded dates to be reported. Exact split dates and forecasting evaluation have not yet been implemented.

## Service selection for this study

Use **wp as the main series** for exploratory analysis and forecasting. Keep **doktor as a secondary comparison** over a usable period, mainly from March 2025 onward. These names identify separate websites/services, not different log formats.

| Service | Purpose | Role in this study |
| --- | --- | --- |
| wp | Public WordPress website with the lab blog and research introduction pages | Main forecasting series |
| doktor | Academic paper search web service built using microservices | Secondary comparison |
| rudder | Internal lab introduction website protected by Google Account SSO | Excluded from the main forecasting study |

Service descriptions: [dataset documentation](https://github.com/cdsl-research/website-access-logs-public#services).

The audited wp series has a longer usable history, more requests and fewer unknown hours than doktor over their respective exported date ranges (see the service totals above). Much of doktor's early archive repeats the same 66-request log from 29 March 2023; the next unique log begins on 8 March 2025. The full-grid unknown-hour percentage therefore also reflects different periods of usable coverage.

Within wp, compare total requests, identified monitoring requests and other requests. Other requests can include bots and scanners and should not be interpreted as human visitors.

The [published dataset statistics](https://github.com/cdsl-research/website-access-logs-public#dataset-statistics) list only 478 rudder entries across 478 files, before deduplication. Rudder has not been independently audited here and is not included in the prepared time series.

Select the final modelling period after accounting for wp's known gaps. This recommendation selects a service; it does not establish the most accurate forecasting model.

## Interpretation and limits

Unknown hours mean no recorded requests, not confirmed zero traffic or confirmed outages. Complete days mean records exist in all 24 hours; this does not prove complete logging within each hour.

Folder/event-month differences describe backup contents and are not automatically timestamp errors. Only event endpoints are checked against folder months.

Exact-duplicate checks use existing audit hashes. Source files were not rehashed or reparsed. Partially overlapping files are not deduplicated by the preparation script. Repeated requests cannot safely be deleted merely because timestamps or lines match.

The local log files use Windows line endings (CRLF). Their byte sizes and SHA-256 hashes therefore differ from the original LF files, while request counts are unchanged. The audit describes the local copies.

See quality_checks.csv for failed consistency checks, missing_intervals.csv for all gaps, date_mismatches.csv for folder/date differences, overlapping_ranges.csv for timestamp overlap candidates, and quality_summary.csv for service totals.
