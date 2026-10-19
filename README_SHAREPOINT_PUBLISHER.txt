COMMERCIAL MTM - SHAREPOINT PUBLISHER 1.0 PILOT

PURPOSE
Generate one upload-ready, self-contained HTML report from two saved reviewed
snapshot versions. This is a separate publisher, not a replacement local app.
No upload, public hosting, network listener, or SharePoint permission change.

INSTALL
Place publish_sharepoint_report.py and PUBLISH_SHAREPOINT_REPORT.cmd beside your
working local_date_app.py and snapshot_manager.py. Keep your existing workspace
folder, archive and local_date_selections.json in their current locations.
Do not copy these scripts into workspace. No new Python packages are required
by the publisher itself; the existing snapshot manager's dependencies still apply.

GENERATE
1. In your local dashboard, save reviewed sources for both dates if needed.
2. Run PUBLISH_SHAREPOINT_REPORT.cmd.
3. Choose Current and Prior as YYYY-MM-DD. Enter accepts the suggested newest
   two SAVED REVIEWED dates, which may differ from the newest imported dates.
4. Check the displayed pair and type PUBLISH.
5. Find the timestamped Commercial_MTM_...html and matching _manifest.json beside
   the launcher. No previous publication is overwritten.

PILOT / UPLOAD
Open the generated HTML locally in your corporate browser. Compare the same
reviewed pair and the five default filters with the working local dashboard.
Check full-precision MTM, Fee, Total, regional/grand totals, matched records and
New Deals. The manifest includes unfiltered and default-filtered control totals
and a separately calculated default-scope distinct New Deals count. These are
checks on the packaged payload, not independent source-workbook reconciliation.
Then upload ONLY the generated HTML using the SAME successful method/location
as your Commercial_MTM_SharePoint_Test.html on SequentReporting / Learning Material.
Keep the manifest locally for audit/reconciliation. Do not upload Python/CMD files.
Do not replace the accepted report until the pilot passes. Use a new report link
for the pilot. Stable-link replacement behavior has not been verified.

VIEWER SCOPE
- Fixed Current/Prior pair; date selectors disabled.
- Original hierarchy, five default filters, measure/mode controls and scripts
  are packaged from the existing workspace, not recreated.
- New Deals renderer uses Current + match(row) + normalized New Deal classification
  and distinct trimmed nonblank DealID labels. No C-Shift alias.
- All rows for the selected pair are embedded, including rows excluded by the
  five defaults. Users can change filters. Filters are NOT security boundaries.
- Publisher does NOT capture your currently open browser's ad hoc filter choices.
- Import/source review/date refresh controls are not included; no local server
  calls are used. Browser storage references use session-only in-memory storage.
- Export/print scripts are retained but require actual SharePoint sandbox testing.
- This is read-only reporting, not DRM: recipients receive the embedded data.

PACKAGING / SAFETY
Data is losslessly gzip-compressed and base64-embedded. Browser decoding uses
DecompressionStream; code is executed through inline script elements, without
fetch, eval, external CDN scripts, or browser persistent storage in the report.
This is more than the first simple SharePoint compatibility test verified.
The optional Commercial_MTM_Publisher_Compatibility_Test.html exercises this
packaging path with NO business data. Use it if the actual report fails to load.
The publisher rejects unknown adapter anchors and network-dependent scripts,
missing fields, invalid dictionary indexes, invalid financial values, missing
five-default rules and defaults with no matching labels.
It enforces a conservative 10,000,000-byte HTML ceiling AFTER compression and
bundling. Oversized builds emit a BLOCKED manifest, not an HTML report. No data
is silently dropped to fit. The file is generated, not automatically accepted.
Node --check runs if Node is already installed; Node is not required to generate.
No workspace/source/selection/archive file is deliberately edited. Importing
Python modules may create normal __pycache__ files; the existing manager's pair
validation is reused and may take its normal archive lock.

ROLLBACK
The working app is not replaced. Delete the publisher files to remove this add-on.
For a failed pilot, retain the previous accepted SharePoint report/link and remove
the failed pilot. Do not delete archived snapshots or reviewed selections.

VALIDATION LIMITATIONS
Actual workspace.js, workspace.css, xlsx_export.js, snapshot_manager.py, reviewed
selections and archive were not available together for end-to-end testing here.
The actual supplied HTML adapter WAS inspected and its exact anchors tested.
Tests used empty-row packaging fixtures and a minimal core-interface stub, not
simulated business data. A browser binary was unavailable; no real-browser or
SharePoint end-to-end test was completed. Full financial/source reconciliation,
real file size, load performance, export/print and sandbox execution remain local
release gates. If stopped, keep the exact message and do not bypass checks.
