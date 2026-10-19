# Arbitrary two-date comparison: source mapping and implementation plan

## Scope of this delivery
The included code changes only the daily source launcher and adds a visible Reset columns button. It does not enable multi-file history, change any measure or hierarchy, implement MTD, or reclassify deals. The following is the researched plan for the next capability, not a claim that it is already implemented.

## Confirmed from the supplied workbook's stored values
Source sheet: DPR_RiskAnalysis. Dated population: 209,322 rows.

| Purpose | Source field | Source column | Status |
|---|---|---:|---|
| Reporting snapshot | EODDATE | 2 | Use for valuation-date selection, never filename date |
| Trade date | TRADEDATE | 3 | Candidate inception-date input; not an approved booking/amendment definition |
| Deal identity | DEALID | 4 | Candidate deal-level key; not unique at row level |
| Storage linkage | STORAGEDEALID | 5 | Preserve for identity investigation |
| Delivery period | LEGMONTH / ContractMonth | 7 / 64 | Absolute delivery month is the candidate common comparison axis |
| Deal start / end | DEALSTARTDATE / DEALENDDATE | 8 / 9 | Do not substitute for trade date or snapshot date |
| Deal type | DEALTYPE | 11 | Existing display/filter dimension |
| Source currency | CURRENCY | 43 | CAD and USD both present; measure conversion basis still requires confirmation |
| Forward year grouping | Year Group | 71 | Existing Year2 fallback; values 2026, 2027, 2028, 2029, 2030 Fwd. |
| MTM | Economic Disc MTM | 72 | Preserve existing measure |
| Fee | Disc Fee | 73 | Preserve existing measure |
| Source total | Disc Fee + Disc MTM | 74 | Reconciliation field; dashboard Total remains MTM + Fee |
| Activity Bucket | Activity Bucket | 91 | Preserve existing top hierarchy level |
| Strategy | Revised Strategy | 92 | Display grouping, not a stable identity key |
| Forward inclusion flag | Fwd_Month_Incl | 93 | Preserve source values; do not silently apply |
| Daily source classification | New Deal / C-Shift | 101 | Preserve original daily flag; not automatically valid for arbitrary intervals |
| Deal-type inclusion flag | Valid Econ Deal Type | 102 | Preserve source values; do not silently apply |

Region occurs twice in the source header. The existing last-column mapping must remain explicit and unchanged. All eight display levels and required slicers remain intact.

## What the actual source demonstrates
- 2026-10-13: 104,182 rows; all carry the stored `Curve Shift` flag.
- 2026-10-14: 105,140 rows; 104,321 carry `Curve Shift` and 819 carry `New Deal`.
- All 819 New Deal-flagged rows have TRADEDATE later than 2026-10-13 in this supplied file. This is an observation, not proof of the generating formula or a universal rule.
- There are 22,860 distinct DEALID values on October 13 and 23,437 on October 14. The endpoint sets have 577 current-only deal IDs and no prior-only deal IDs.
- 47,763 (EODDATE, DEALID, ContractMonth) groups contain multiple rows. That grain is not a unique raw-record key. These are not automatically duplicates.
- CURRENCY contains 4,138 CAD rows and 205,184 USD rows. This does not establish the denomination of the chosen Economic Disc MTM/Disc Fee measures. Do not introduce FX conversion or assume mixed-currency summation is approved.

Detailed machine-readable findings are included in source_mapping_findings.json. All counts refer to source rows or explicitly named groups, not unique deals unless stated.

## Recommended product behavior
Provide two selectors: Current snapshot and Baseline snapshot. List only dates in a validated snapshot catalog; require Current later than Baseline. Show actual dates, source filenames, publication versions, and population context.

Calculate each measure as:

Change = Current endpoint value - Baseline endpoint value
Total Value = Economic Disc MTM + Disc Fee

No daily-balance summation. No source workbook writes, recalculation, refresh, or macro execution. Call the result valuation change, not realized P&L or explained curve movement.

MTD can later be a shortcut that selects an approved prior-month-end snapshot. It should not be a separate arithmetic engine. Missing dates remain unavailable; no silent substitution.

## Historical snapshot storage
1. Ingest the published daily file once, not on every browser interaction.
2. Store normalized records partitioned by EODDATE, with source hash, original source row, schema version, measure mapping, currency-basis status, and control totals.
3. A date appearing in several daily files must not be appended twice. Compare canonical normalized content/control totals; a whole-file hash alone cannot establish identical snapshot contents.
4. If the same date is republished with different contents, retain both versions and require an explicit authoritative version. Do not silently overwrite history.
5. Keep source daily files or an authorized immutable archive. The current two-date workbook cannot recover a missing historical month-end.
6. Publish only the selected two snapshots to the browser initially. Do not put the entire archive into a single data.js file.
7. A pure file:// page cannot be assumed to browse arbitrary network files automatically. Use a local Python pair-publisher (or an approved service) to load the selected cached pair, then open the generated dashboard. A server-backed date picker is a separate deployment decision.

## Period alignment
Use absolute ContractMonthDate as the comparison axis. A Year2 bucket label can change with reporting date, so matching only on Year2 can manufacture additions/removals. Preserve the source bucket for audit; agree a common presentation bucket rule before changing the current Year2 behavior. No such remapping is applied in this patch.

Decide whether the pair covers all source delivery months, a common fixed range, or a current-forward range. These are different analytical scopes. Display the selected scope explicitly; never silently drop expired delivery months from the baseline.

## Identity versus display hierarchy
Keep the eight-level hierarchy for navigation. Do not use strategy, region, curve, or counterparty labels as the sole deal-identity key: a reassignment can move the same deal between branches.

Before position-level attribution, establish the raw row grain. Investigate deal + leg/component + delivery month + valuation pool + currency and any other source discriminator. Preserve all rows and legitimate components. Do not deduplicate based on DEALID or identical financial values.

For simple valuation totals, endpoint aggregation does not require a unique raw-record match. For explaining why values changed, it does.

## New / existing / absent classifications
Keep these separate:
- Current-only position: source presence in current only at the approved comparison grain.
- Prior-only position: source presence in baseline only.
- Present at both endpoints: source presence at both, even if values are zero.
- Candidate new since baseline: candidate inception/booking date within (Baseline, Current], using an approved deal-level rule.
- Late-entered/backdated: requires booking/audit timestamps not yet established.
- Amendment/cancellation/rolloff/reassignment: requires status, version, and lifecycle rules not yet established.

Do not call all current-only positions New Deals. Do not call all movement on existing deals Curve Shift. The stored daily New Deal / C-Shift flag must remain a separate source attribute until its formula and reference date are verified.

The supplied file's TRADEDATE relationship supports investigating a date-based rule, but does not settle backdating, amendments, cancellations, intraperiod deals that disappear before both endpoints, or daily-flag reset behavior. An endpoint-only view cannot identify all activity that occurred and vanished between the two dates; lifecycle/event history would be required.

## Approval checklist before enabling arbitrary dates
- Confirm the approved snapshot version per EODDATE and history retention location.
- Confirm measure denomination/FX basis and economic/realized/settled scope.
- Confirm absolute delivery-month alignment and common forward-bucket display rule.
- Confirm source inclusion flags and preset rules separately from raw population.
- Establish position grain and legitimate multirow components.
- Confirm new-deal inception/booking rule, amendments, cancellations, and late/backdated treatment.
- Confirm classification as-of convention when a deal changes hierarchy branch.
- Test month boundary, year boundary, same-date republication, missing baseline, zero-value positions, and a long interval.

## Runtime: what is known and what must be measured
No prospective runtime estimate is asserted. The user's previously supplied v0.2.1 log records 2026-10-16 00:37:49.239005 UTC through 00:40:03.023635 UTC: 133.784630 seconds for that past full extraction/comparison run. This is not a benchmark of the new launcher, browser, historical archive, or network transfer.

Recommended architecture separates:
- Cold ingest: copy + container checks + XLSB read + normalize + controls + cache write.
- Cached pair publish: read two cached snapshots + aggregate + serialize.
- Browser interaction: initial load + selected-pair aggregation/rendering.

The delivered launcher writes daily_build_timing.json with measured sourceCopySeconds, extractAndPublishSeconds, totalSeconds, source size/hash, valuation dates, and success/failure. Total includes additional checks and publishing; it need not equal the sum of the two named substeps. These are observations from the actual run, not forecasts.

Use repeated actual runs on the user's workstation/network and report measured median and slowest observed values. Record browser pair-switch time separately. Network throughput, file size, raw row count, cache format, antivirus scanning, and hardware have not been measured here. Two cached endpoints should be the unit of work, rather than rescanning every file in the archive for every selection; this is a design recommendation, not a guaranteed response time.
