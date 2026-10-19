# Snapshot importer and date-pair publisher v0.5

## First use
1. Extract all package files into your existing main project folder, beside the `workspace` folder. Do not put them inside `workspace` or `comparison_data`.
2. Run **IMPORT_SNAPSHOTS.cmd**. It uses the Commercial MTM folder already saved in daily_source_config.json. If that configuration is absent, a folder picker appears.
3. The importer reads matching daily workbooks, including names such as `10-16-2026 TPORT_MTM_COMMERCIAL.xlsb`, and archives the valuation dates found inside each file.
4. Run **PUBLISH_DATE_PAIR.cmd**. Choose Current and Baseline from the available valuation dates. Current must be later than Baseline.
5. If a date has more than one stored version, select its source/version explicitly. No version is automatically preferred. Then select **Publish selected pair**.
6. The historical dashboard opens from a new `history_views` subfolder. It copies your installed dashboard's UI assets, including the v0.4 visual layer and Reset columns patch if installed. Your normal daily dashboard is not replaced.

For your first nonadjacent test, choose Current **2026-10-15** and Baseline **2026-10-13**, provided the daily files import those dates. File dates are not valuation dates. The October 16 filename previously inspected contains October 14 and 15 valuations.

## Normal workflow
- After new daily files arrive, run IMPORT_SNAPSHOTS.cmd again. An unchanged source file is not extracted twice. The file is still copied/hashed and referenced payloads checked before it is skipped.
- Run PUBLISH_DATE_PAIR.cmd whenever you want another pair.
- LIST_SNAPSHOT_DATES.cmd prints available dates, versions, row counts, totals, and source filenames.
- OPEN_LAST_DATE_PAIR.cmd reopens the most recently published historical view.
- Continue using BUILD_DAILY_WORKSPACE.cmd for the normal daily dashboard. It does not update the historical archive automatically; run the importer separately.

**This is a local date-selection launcher, not a new in-browser archive browser.** Each published dashboard contains exactly the selected two snapshots. The existing dashboard date controls can operate only on those loaded endpoints. To select another archived pair, use PUBLISH_DATE_PAIR.cmd again.

## What is preserved
- Activity Bucket > Region > AMA / NON-AMA > Strategy > Deal Type > Curve > Counterparty > Deal No.
- Existing required slicers and source-relative flag values.
- Your installed UI assets, original daily data.js, and original source workbooks.
- The existing browser's MTM, Fee, and Total Value calculations. Total Value remains MTM + Fee; change remains Current - Baseline.
- All dated source rows, including legitimate repeated deal/month components. No financial-row deduplication, report exclusions, currency conversion, or attribution rules are introduced.

The importer uses the previously established raw-population field mapping. Region uses the last Region header; Year2 prefers an actual Year2 column and otherwise uses Year Group. Blank measures follow the existing zero convention; nonnumeric/error measures stop the file import. Dates and dimension labels are normalized for the browser contract. Raw stored rows are also retained for audit.

Before publishing, the package checks that the installed workspace/data.js column schema matches the supported contract. A mismatch stops publishing rather than rewriting your core code. No original daily files are overwritten.

## Snapshot versions and overlapping dates
The archive stores:
- Snapshot valuation date from EODDATE.
- Source file SHA-256, filename, observed path, size, modification time, and import time.
- Source schema and field mapping.
- Row counts and MTM/Fee/Total control totals.
- A full raw-row multiset fingerprint, preserving duplicate-row multiplicity but ignoring row order.
- A separate financial-field fingerprint, excluding daily classification flags.
- Compressed normalized values plus original stored rows and source row numbers.

Identical snapshot contents from another source file are referenced as one version, not appended. If raw contents differ, both versions are retained. This includes cases where financial totals match but New Deal / C-Shift or other source fields differ. Version selection is explicit; the software does not decide which report is authoritative.

Payload source-row numbers refer to the first source file that created that payload version. That origin source hash is retained separately from all other files referencing the same contents.

The same XLSB reader must be used for new files throughout an archive. Mixing reader representations can create artificial version differences, so the importer blocks a reader change for new sources. Use a new archive only after an explicit migration decision.

## Source discovery and readiness
- The matcher is `*TPORT_MTM_COMMERCIAL*.xlsb` in the configured daily folder.
- Lock files beginning with `~$` are excluded.
- The nightly Endur/AutoFiles/RISK folder is disallowed, including explicit file imports.
- The `History` subfolder is not scanned by default. Optional CLI `--include-history` includes matching files directly inside that one subfolder, not arbitrary recursive folders.
- A local temporary copy is made, and size/modified-time changes during copying stop that file. XLSB container integrity is checked before extraction.
- These checks reduce partial-copy risk. They do not prove that the 6 AM business process completed or that formulas were freshly recalculated.
- No macros, Excel refresh, formula recalculation, or workbook saves occur.
- Each file commits its snapshots to the catalog only after successful extraction. A failed file does not erase snapshots imported successfully from other files. Review the import log if a run reports partial failure.

## Historical interpretation: important limits
This release is **raw endpoint valuation comparison**, not official P&L or explained movement attribution.

New Deal / C-Shift remains the selected source report's daily attribute. It is not recalculated for the selected interval. A persistent banner and Snapshot sources dialog make that context visible. Existing flag slicers remain available, but filtering on them across dates is not an approved interval new-deal analysis.

All source delivery months and existing Year2 labels are retained. No common-period restatement is performed. For distant dates, source-relative Year2 labels or forward-inclusion flags may shift; use the absolute ContractMonth slicer for a consciously selected common delivery range. Total valuation differences are still endpoint subtraction, but a bucket movement is not necessarily an economic movement.

Currency basis and lifecycle attribution remain unresolved as documented in the earlier two-date plan. No FX conversion is added. Current-only is not automatically New Deal, and existing-deal movement is not automatically Curve Shift. Missing snapshots are rejected, not filled with zero. A genuinely absent position within two loaded snapshots follows the existing zero-on-absent-side aggregation behavior.

## Output folders
- `snapshot_archive/catalog.json`: authoritative version catalog.
- `snapshot_archive/snapshots/<date>/<version>.jsonl.gz`: immutable version payloads.
- `snapshot_archive/available_dates.json`: readable date/version inventory.
- `snapshot_archive/last_import.json` and `snapshot_archive/logs/`: actual import results and measured durations.
- `snapshot_archive/last_pair.json`: pointer to the last successfully published historical page.
- `history_views/<current>_vs_<baseline>_<run>/`: complete selected-pair page, copied UI assets, data.js, build_report.json, source_records.csv.gz, and pair_publish_timing.json.

Pair views are staged in a new folder and renamed only after all outputs succeed. The last-pair pointer changes afterward. A failed build leaves the previous published view available. A crash can leave a `.pending_...` folder or unreferenced archive payload; these are not automatically treated as published views.

Each publish creates a separate view folder. No automatic retention/deletion policy is applied. Archive and views contain company financial data; keep the main project and temporary-storage location within approved access/storage controls. Standard operating-system temp storage is used for workbook copies and is cleaned on normal exit; forced termination may leave temp files.

Do not run concurrent import/publish operations. The archive uses an exclusive lock. If a process crashes, verify it is no longer running before manually removing `snapshot_archive/archive.lock`. Do not remove an active lock.

## Runtime
The software records observed import and publish durations. It does not predict runtime. Import reads new workbooks once; publishing reads only the two selected cached snapshots, not the whole daily folder. Repeated imports still incur file copy/hash and cache-integrity checks. Browser loading is a separate measurement from Python publishing.

## Python requirements
Python 3.9 or newer, with tkinter for the date-selection window, and pyxlsb for reading XLSB files. The package does not silently install dependencies or require a server. If pyxlsb is missing, use your approved Python environment or:

```cmd
py -m pip install pyxlsb
```

Optional advanced reader: python-calamine via `--reader calamine`. It was used for the full supplied-workbook test. It may use more memory; do not switch readers within an existing archive.

All CMD launchers call the script by absolute path and do not pass a quoted trailing-backslash project argument. They do not depend on CMD's current directory, including when launched from a UNC share. Windows/company execution and network permissions still apply.

## Command-line equivalents
Run from the main project folder, or supply an explicit `--project` main-folder path without a trailing backslash inside the quotes.

```cmd
py snapshot_manager.py import
py snapshot_manager.py list
py snapshot_manager.py choose
py snapshot_manager.py open-last
```

Explicit pair, when each date has one version:

```cmd
py snapshot_manager.py publish --current 2026-10-15 --baseline 2026-10-13 --open
```

If a date has multiple versions, add `--current-version` or `--baseline-version` using a unique version prefix from LIST_SNAPSHOT_DATES.cmd. GUI selection is recommended.

Explicit source folder or files:

```cmd
py snapshot_manager.py import --folder "O:\your-approved-Commercial-MTM-folder"
py snapshot_manager.py import --files "O:\your-approved-Commercial-MTM-folder\10-16-2026 TPORT_MTM_COMMERCIAL.xlsb"
```

Those example paths are placeholders, not an inferred Williams folder path. The normal launcher uses your already saved daily folder.

## Testing and limits
TEST_RESULTS.json documents actual supplied-workbook controls and exercised safeguards. A full import and pair publish were run on the available October 13/14 workbook, without synthetic financial records. Default pyxlsb header/date access was also exercised. The original installed v0.3/v0.4 core files and Windows native date-picker environment were not available here; asset preservation and browser data/provenance behavior were tested against a minimal, non-distributed compatibility harness. Full live Windows integration and the three-file October 15 comparison must be exercised on your workstation.

The package contains code and instructions only. It does not bundle a financial archive, replace your daily dashboard, or claim that the live network folder has already been imported.
