Commercial MTM 0.8.1 - repair candidate, not a fully reconciled release

INSTALL
1. Stop the dashboard with Ctrl+C.
2. Extract all package files beside the current local_date_app.py.
3. Run INSTALL_REPAIR_0_8_1.cmd. No manual renaming or code editing.
4. If installed, restart with your existing launcher.

The installer makes a unique timestamped backup and runs the candidate --check
BEFORE replacing the current app. Adapter mismatch stops installation and leaves
the app unchanged. Read REPAIR_0_8_1_INSTALL_LOG.txt if installation stops.
No archive, source workbook, workspace asset, or saved-selection file is edited.
Node syntax checks run locally if Node is already available; no install required.

IMPORTANT LIMITATION
Only the Python baseline was attached. The actual HTML visual adapter and actual
classification dictionary could not be inspected here. This candidate recognizes
one specific inline adapter shape: one m !== 'Movements' gate, one parameterless
countMovements declaration, and one standalone countMovements(); invocation.
It deliberately refuses other shapes. If rejected, attach workspace/index_v0_4.html
(or index.html) and the install log. Do not bypass the guards.
The adapter patch is applied in memory only. The financial gate becomes an MTM,
Fee, Total allowlist. The obsolete movement renderer is retired before it can
queue callbacks; its original body is retained unreachable. No movement callback
from an old browser page is reused after restarting/reloading.

CHANGES
- New Deals owns title, integer value, subtitle and neutral styling.
- Distinct trimmed nonblank DealID labels; applied Current; existing match(row).
- Classification normalized by trim/lowercase only; no C-Shift aliases.
- Missing columns/dictionaries or calculation errors show Unavailable.
- pending/ready/error plus aggregation generation/current-date completion check.
- Disabled Raw population toolbar control hidden with targeted !important CSS.
- Data info fixed-position viewport sizing, internal scrolling, theme surfaces,
  Escape closing and focus return. Status remains outside the disclosure.

CLASSIFICATION REVIEW
After load, browser console window.PNL_NEW_DEALS_CLASSIFICATIONS contains the
actual classification labels. Verify the intended New Deal label there. The
package does not invent aliases. No actual dictionary was available for testing.

LOCAL RELEASE GATE
Use identical reviewed sources, dates and five filters. Compare full-precision
MTM/Fee/Total, grand/regional totals and record counts to your baseline.
Independently count distinct qualifying Current DealID values in the source.
Check Region/filter changes, measure/mode independence, Prior-only changes,
zero counts, print, source review, theme readability and popup keyboard use.
Fixture tests do not replace these local checks.

ROLLBACK
Stop the app; run RESTORE_REPAIR_0_8_1.cmd; restart with the existing launcher.
This restores the backup recorded by the most recent install attempt.
Keep the timestamped backups if you want to restore an earlier attempt.
