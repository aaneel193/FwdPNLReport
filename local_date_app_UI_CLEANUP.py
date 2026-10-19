#!/usr/bin/env python3
"""
Commercial MTM local date-comparison prototype.

Required existing files:
    snapshot_manager.py
    snapshot_archive/catalog.json
    workspace/index_v0_4.html (or index.html)
    workspace/workspace.js
    workspace/workspace.css
    workspace/xlsx_export.js
    workspace/data.js

Run:
    py local_date_app.py

Preflight only:
    py local_date_app.py --check

Original dashboard files, source workbooks, and archived snapshots
are not modified. Timing logs are written to local_date_logs/.
Explicit source choices are saved to local_date_selections.json beside this script.
No source version is automatically approved, including single-version dates.

This application is for local, single-user testing only.
"""

import argparse
import gzip
import importlib.util
import json
import math
import os
import re
import secrets
import sys
import threading
import time
import webbrowser

from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT / "workspace"

SESSION_TOKEN = secrets.token_urlsafe(32)
COOKIE_NAME = "mtm_local_" + secrets.token_hex(6)

PAIR_LOCK = threading.Lock()
LOG_LOCK = threading.Lock()
SELECTION_LOCK = threading.Lock()

MANAGER = None
PATCHED_CORE = None
PAGE_NAME = None


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def encode_json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


# Injected into the served copy of workspace.js only.
# The original workspace.js on disk is never edited.
CORE_EXTENSION = r"""
function replaceData(next) {
    if (!next || !next.meta || !next.dicts ||
        !Array.isArray(next.rows)) {
        throw new Error('Invalid date-pair payload.');
    }

    if (JSON.stringify(next.columns) !== JSON.stringify(D.columns)) {
        throw new Error('Selected pair has a different column schema.');
    }

    const current = next.meta.current;
    const prior = next.meta.prior;

    if (!/^\d{4}-\d{2}-\d{2}$/.test(current || '') ||
        !/^\d{4}-\d{2}-\d{2}$/.test(prior || '') ||
        current <= prior) {
        throw new Error('Invalid Current / Prior dates.');
    }

    const dimensions = ['Date', ...fields];

    for (const key of dimensions) {
        if (!Array.isArray(next.dicts[key]) ||
            next.dicts[key].some(v => typeof v !== 'string')) {
            throw new Error('Invalid dictionary: ' + key);
        }
    }

    for (const row of next.rows) {
        if (!Array.isArray(row) || row.length !== D.columns.length) {
            throw new Error('Invalid archived record width.');
        }

        for (const key of dimensions) {
            const index = row[I[key]];
            if (!Number.isInteger(index) ||
                index < 0 ||
                index >= next.dicts[key].length) {
                throw new Error('Invalid dictionary index: ' + key);
            }
        }

        const reportingDate = next.dicts.Date[row[I.Date]];

        if (reportingDate !== current && reportingDate !== prior) {
            throw new Error('Unexpected valuation date in payload.');
        }

        if (!Number.isFinite(row[I.MTM]) ||
            !Number.isFinite(row[I.Fee])) {
            throw new Error('Invalid financial measure in payload.');
        }
    }

    const previous = {
        meta: D.meta,
        rows: D.rows,
        dictionaries: {...dict},
        state: {
            ...S,
            expanded: new Set(S.expanded),
            periodOpen: new Set(S.periodOpen)
        },
        buildTime: $('buildTime').textContent,
        notes: notes.textContent,
        undoHidden: $('undo').hidden
    };

    const filters = {};
    const unavailable = [];

    for (const [key, selection] of Object.entries(S.filters)) {
        if (selection == null) {
            filters[key] = null;
            continue;
        }

        if (!Array.isArray(next.dicts[key])) {
            throw new Error('Active filter field missing: ' + key);
        }

        // Retain label intent even if a label is absent from one pair.
        // Manual filter edits create a new Set in the existing core.
        const selectedLabels = selection._pnlLabels
            ? [...selection._pnlLabels]
            : [...selection].map(index => dict[key][index]);

        const lookup = new Map(
            next.dicts[key].map((label, index) => [label, index])
        );

        const mapped = new Set();

        for (const label of selectedLabels) {
            if (lookup.has(label)) {
                mapped.add(lookup.get(label));
            } else {
                unavailable.push(key + ': ' + label);
            }
        }

        mapped._pnlLabels = selectedLabels;
        filters[key] = mapped;
    }

    // Cancel queued aggregation for the previous pair.
    ++epoch;
    updating = true;

    try {
        if ($('filterDialog').open) $('filterDialog').close();
        if ($('detailDialog').open) $('detailDialog').close();
        activeDim = null;

        // Preserve object identities used by the visual adapter.
        D.meta = next.meta;
        D.rows = next.rows;
        Object.assign(dict, next.dicts);

        S.current = current;
        S.prior = prior;
        S.filters = filters;
        S.undo = null;
        $('undo').hidden = true;

        // Existing aggregation, hierarchy, and financial formulas.
        aggregate();

        $('buildTime').textContent =
            'Pair loaded ' +
            D.meta.generatedUtc.replace('T', ' ').slice(0, 19) +
            ' UTC';

        notes.textContent =
            'Source mapping notes: ' +
            (D.meta.warnings || []).join(' ');

        return {unavailableFilterLabels: unavailable};

    } catch (error) {
        D.meta = previous.meta;
        D.rows = previous.rows;
        Object.assign(dict, previous.dictionaries);
        Object.assign(S, previous.state);
        $('undo').hidden = previous.undoHidden;

        try {
            aggregate();
            $('buildTime').textContent = previous.buildTime;
            notes.textContent = previous.notes;
        } catch (rollbackError) {
            console.error('Rollback redraw failed:', rollbackError);
            $('gridScroll').style.visibility = 'hidden';

            throw new Error(
                'Pair replacement and rollback redraw failed. ' +
                'Reload before using the results.'
            );
        }

        throw error;

    } finally {
        updating = false;
        document.body.classList.remove('loading');
    }
}
"""


CLIENT_JS = r"""
(() => {
    'use strict';

    const $ = id => document.getElementById(id);

    let catalog = null;
    let busy = false;
    let refreshing = false;
    let reviewing = false;
    let appliedVersions = {};
    let latestTiming = null;

    function make(tag, text) {
        const node = document.createElement(tag);
        if (text !== undefined) node.textContent = text;
        return node;
    }

    async function api(path, options = {}) {
        const response = await fetch(path, {
            ...options,
            cache: 'no-store',
            credentials: 'same-origin'
        });

        if (!response.ok) {
            const body = await response.json().catch(() => ({
                error: 'Local application request failed.'
            }));
            throw new Error(body.error || 'Request failed.');
        }

        return response;
    }

    function version(role) {
        return $(role + 'Version').value;
    }

    function pending() {
        const state = PNL_APP.state;

        return (
            $('current').value !== state.current ||
            $('prior').value !== state.prior ||
            version('current') !== (appliedVersions.current || '') ||
            version('prior') !== (appliedVersions.prior || '')
        );
    }

    function updateButtons() {
        const blocked = busy || refreshing;
        const exportBlocked = blocked || pending();

        $('export').disabled = exportBlocked;
        $('print').disabled = exportBlocked;

        $('applyDates').disabled = blocked || !catalog;
        $('refreshDates').disabled = blocked;
        $('downloadTiming').disabled = busy || !latestTiming;
        $('saveSources').disabled = blocked || !catalog;
        $('reviewSources').disabled = blocked || !catalog;

        for (const id of [
            'current', 'prior', 'currentVersion', 'priorVersion'
        ]) {
            $(id).disabled = blocked || !catalog;
        }
    }

    function showStatus() {
        if (busy) return;

        const state = PNL_APP.state;

        $('pairStatus').textContent =
            'Displayed: ' + state.current + ' vs ' + state.prior +
            (pending()
                ? ' · Requested dates/versions are not applied.'
                : '') +
            (catalog && needsReview() ? ' · Source review required: choose and save a source for each unreviewed date.' : '');

        updateButtons();
    }

    function savedVersion(role) {
        const day = $(role).value;
        const saved = catalog?.savedSelections?.[day]?.version || '';
        return (catalog?.dates?.[day] || []).some(x => x.version === saved)
            ? saved : '';
    }
    function needsReview() {
        return !savedVersion('current') || !savedVersion('prior');
    }
    function updateReview() {
        const visible = reviewing || needsReview();
        for (const role of ['current', 'prior']) {
            $(role + 'Version').closest('label').hidden = !visible;
        }
        $('saveSources').hidden = !visible;
        $('reviewSources').textContent = visible ? 'Cancel source review' : 'Review sources';
        updateDataInfo();
    }
    function fillVersions(role) {
        const items = catalog.dates[$(role).value] || [];
        const select = $(role + 'Version');
        select.replaceChildren();
        const placeholder = make('option', 'Choose reviewed source');
        placeholder.value = '';
        select.appendChild(placeholder);
        for (const item of items) {
            const option = make('option', item.version.slice(0, 12) +
                ' | ' + item.rows.toLocaleString() + ' rows | ' + item.files.join(', '));
            option.value = item.version;
            select.appendChild(option);
        }
        select.value = savedVersion(role);
        updateReview();
    }
    async function saveSources() {
        if (busy || refreshing || !catalog) return;
        const dates = {};
        for (const role of ['current', 'prior']) {
            const day = $(role).value;
            const selected = version(role);
            if (!selected) {
                $('pairStatus').textContent = 'Choose and review a source for both dates before saving.';
                return;
            }
            if (dates[day] && dates[day] !== selected) {
                $('pairStatus').textContent = 'One date cannot have two saved source versions.';
                return;
            }
            dates[day] = selected;
        }
        setBusy(true);
        try {
            await api('/api/selections', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({dates})
            });
            for (const [day, selected] of Object.entries(dates)) {
                catalog.savedSelections[day] = {version: selected};
            }
            reviewing = false;
            updateReview();
            $('pairStatus').textContent = 'Reviewed sources saved. Press Apply to load the selected dates.';
        } catch (error) {
            $('pairStatus').textContent = 'Source selection was not saved: ' + error.message;
        } finally { setBusy(false); }
    }

    async function refreshDates() {
        if (busy || refreshing) return;

        const old = {
            current: $('current').value,
            prior: $('prior').value,
            currentVersion: version('current'),
            priorVersion: version('prior')
        };

        refreshing = true;
        updateButtons();

        try {
            const nextCatalog =
                await (await api('/api/catalog')).json();

            const dates = Object.keys(nextCatalog.dates).sort();

            if (dates.length < 2) {
                throw new Error(
                    'At least two archived dates are required. ' +
                    'Run IMPORT_SNAPSHOTS.cmd first.'
                );
            }

            catalog = nextCatalog;
            catalog.savedSelections = catalog.savedSelections || {};

            for (const role of ['current', 'prior']) {
                const select = $(role);
                select.replaceChildren();

                for (const date of dates) {
                    const option = make('option', date);
                    option.value = date;
                    select.appendChild(option);
                }

                const preferred = old[role] || PNL_APP.state[role];

                select.value = dates.includes(preferred)
                    ? preferred
                    : role === 'current'
                        ? dates[dates.length - 1]
                        : dates[dates.length - 2];

                fillVersions(
                    role,
                    old[role + 'Version'] ||
                    appliedVersions[role]
                );
            }

            $('archiveStatus').textContent =
                'Latest archived valuation: ' + dates[dates.length - 1] +
                ' · Last import: ' +
                (catalog.lastImportFinished || 'Not recorded') +
                ' · Import status: ' +
                (catalog.lastImportStatus || 'Not recorded');

            showStatus();

        } catch (error) {
            $('pairStatus').textContent =
                'Date catalog refresh failed: ' + error.message;
            console.error(error);

        } finally {
            refreshing = false;
            updateButtons();
        }
    }

    function setBusy(value) {
        busy = value;
        document.body.classList.toggle('pair-loading', value);
        document.body.setAttribute('aria-busy', String(value));
        updateButtons();
    }

    function hideRawPopulationControl() {
        const exact = 'Raw population — no preset';
        for (const select of document.querySelectorAll('select')) {
            if (![...select.options].some(o => o.textContent.trim() === exact)) continue;
            const container = select.closest('label,.field,.control,.filter-control');
            if (container && /Deals/i.test(container.textContent)) {
                container.hidden = true;
                container.dataset.uiCleanupHidden = 'raw-population';
                return true;
            }
        }
        console.warn('Raw population control was not identified; it was left visible.');
        return false;
    }
    function updateDataInfo() {
        const info = $('dataInfo');
        const summary = $('dataInfoSummary');
        if (!info || !summary || !catalog) return;
        if (needsReview()) { info.open = true; summary.textContent = 'Source review required'; }
        else summary.textContent = 'Data info';
    }

    async function settleVisuals() {
        await new Promise(resolve =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))
        );

        const started = performance.now();

        while (
            document.querySelector(
                '.v04-kpi[data-metric="Movements"] .k-value'
            )?.textContent === '…'
        ) {
            if (performance.now() - started > 60000) return false;
            await new Promise(resolve => setTimeout(resolve, 30));
        }

        await new Promise(resolve => requestAnimationFrame(resolve));
        return true;
    }

    function renderSources() {
        const container = $('pairSources');
        container.replaceChildren();

        container.appendChild(
            make('summary', 'Selected snapshot sources')
        );

        const text = make('pre');
        const snapshots = PNL_DATA.meta.selectedSnapshots || [];

        text.textContent = snapshots.length
            ? snapshots.map(item =>
                item.date +
                '\nVersion: ' + item.version +
                '\nSource: ' + item.sourceFiles.join(', ') +
                '\nStored daily flags: ' +
                JSON.stringify(item.sourceFlags || {})
            ).join('\n\n')
            : 'Initial data is from workspace/data.js. ' +
              'Apply an archived pair to show its source versions.';

        text.textContent +=
            '\n\nNew Deal / C-Shift flags remain report-relative, ' +
            'not classifications for the selected interval.';

        container.appendChild(text);
    }

    function downloadTiming() {
        if (!latestTiming) return;

        const blob = new Blob([
            JSON.stringify({
                lastApply: latestTiming,
                note:
                    'Request/body includes server preparation and transfer. ' +
                    'It is not a pure network-transfer measurement.'
            }, null, 2)
        ], {type: 'application/json'});

        const url = URL.createObjectURL(blob);
        const link = make('a');

        link.href = url;
        link.download = 'commercial_mtm_apply_timing.json';
        document.body.appendChild(link);
        link.click();
        link.remove();

        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    async function applyDates() {
        if (busy || refreshing || !catalog) return;

        const current = $('current').value;
        const prior = $('prior').value;
        const currentVersion = savedVersion('current');
        const priorVersion = savedVersion('prior');
        if (reviewing || version('current') !== currentVersion || version('prior') !== priorVersion) {
            $('pairStatus').textContent = 'Save reviewed sources or cancel source review before Apply.';
            return;
        }

        if (current <= prior) {
            $('pairStatus').textContent =
                'Current must be later than Prior.';
            return;
        }

        if (!currentVersion || !priorVersion) {
            $('pairStatus').textContent =
                'Source review required. Choose and save a source for each date.';
            return;
        }

        const started = performance.now();
        let committed = false;

        setBusy(true);

        $('pairStatus').textContent =
            'Loading requested ' + current + ' vs ' + prior +
            '. Displayed results remain ' +
            PNL_APP.state.current + ' vs ' + PNL_APP.state.prior + '.';

        try {
            const query = new URLSearchParams({
                current, prior, currentVersion, priorVersion
            });

            const response = await api('/api/pair?' + query);
            const body = await response.text();
            const received = performance.now();

            const parseStarted = performance.now();
            const next = JSON.parse(body);
            const parsed = performance.now();

            const calculateStarted = performance.now();
            const result = PNL_APP.replaceData(next);
            const calculated = performance.now();

            committed = true;
            appliedVersions = {
                current: currentVersion,
                prior: priorVersion
            };

            $('current').value = PNL_APP.state.current;
            $('prior').value = PNL_APP.state.prior;
            renderSources();

            const visualsConfirmed = await settleVisuals();
            const completed = performance.now();

            latestTiming = {
                observedUtc: new Date().toISOString(),
                current,
                prior,
                currentVersion,
                priorVersion,
                serverPrepareMs: Number(
                    response.headers.get('X-Prepare-Ms')
                ),
                requestAndBodyMs: received - started,
                parseMs: parsed - parseStarted,
                calculationMs: calculated - calculateStarted,
                visualSettleMs: completed - calculated,
                totalApplyMs: completed - started,
                visualsConfirmed,
                records: next.rows.length
            };

            window.PNL_LAST_APPLY_TIMING = latestTiming;

            const missing = result.unavailableFilterLabels;

            $('pairStatus').textContent =
                'Displayed: ' + current + ' vs ' + prior +
                ' · Apply ' +
                (latestTiming.totalApplyMs / 1000).toFixed(2) + ' s' +
                (!visualsConfirmed
                    ? ' · Visual completion not confirmed.'
                    : '') +
                (missing.length
                    ? ' · Selected labels absent from this pair: ' +
                      missing.join('; ')
                    : '');

            $('pairTiming').textContent =
                'Server ' +
                (latestTiming.serverPrepareMs / 1000).toFixed(2) + ' s' +
                ' · Request/body ' +
                (latestTiming.requestAndBodyMs / 1000).toFixed(2) + ' s' +
                ' · Parse ' +
                (latestTiming.parseMs / 1000).toFixed(2) + ' s' +
                ' · Calculate ' +
                (latestTiming.calculationMs / 1000).toFixed(2) + ' s' +
                ' · Visual settle ' +
                (latestTiming.visualSettleMs / 1000).toFixed(2) + ' s';

            api('/api/metrics', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(latestTiming)
            }).catch(error => {
                console.warn('Timing log save failed:', error);
                $('pairTiming').textContent +=
                    ' · Log save failed; use Download timing.';
            });

        } catch (error) {
            $('pairStatus').textContent =
                (committed
                    ? 'New pair loaded, but a later UI step failed. '
                    : 'Apply failed. Previous pair retained unless ' +
                      'a redraw warning is shown. ') +
                'Displayed: ' +
                PNL_APP.state.current + ' vs ' + PNL_APP.state.prior +
                ' · ' + error.message;

            console.error(error);

        } finally {
            setBusy(false);
        }
    }

    function start() {
        if (!window.PNL_APP?.replaceData) {
            console.error('Local date-switch extension unavailable.');
            return;
        }

        const snapshots = PNL_DATA.meta.selectedSnapshots || [];

        appliedVersions = {
            current: snapshots.find(
                x => x.date === PNL_APP.state.current
            )?.version || '',
            prior: snapshots.find(
                x => x.date === PNL_APP.state.prior
            )?.version || ''
        };

        const style = make('style');
        style.textContent = `
            #localDatePanel {
                flex-shrink:0;
                padding:7px 18px;
                background:var(--navy-050,#EEF4FB);
                color:var(--ink-700,#334155);
                border-bottom:1px solid var(--line,#DDE3EA);
                font-size:11px;
                display:flex;
                gap:7px 14px;
                flex-wrap:wrap;
                align-items:center;
                max-height:210px;
                overflow:auto;
            }
            #localDatePanel label {
                display:flex;gap:6px;align-items:center;
            }
            #localDatePanel label[hidden] {display:none}
            #localDatePanel select {
                max-width:340px;font-size:11px;
            }
            #pairStatus {font-weight:600;flex:1;min-width:320px}
            #dataInfo {margin-left:auto;position:relative}
            #dataInfo > summary {cursor:pointer;list-style:none;padding:5px 12px;border:1px solid var(--line,#DDE3EA);border-radius:16px;background:#fff;color:var(--ink-700,#334155);font-weight:600}
            #dataInfo > summary::-webkit-details-marker {display:none}
            #dataInfoBody {position:absolute;right:0;top:31px;z-index:30;width:min(620px,88vw);padding:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;background:#fff;border:1px solid var(--line,#DDE3EA);border-radius:8px;box-shadow:0 10px 28px rgba(15,23,42,.16)}
            #archiveStatus,#pairTiming {font-size:10px;flex-basis:100%}
            #pairSources {flex-basis:100%}
            #pairSources summary {padding:2px 0;font-size:10px}
            #pairSources pre {
                white-space:pre-wrap;overflow-wrap:anywhere;
                font:11px Segoe UI,Arial,sans-serif;margin:6px 0;
            }
            #applyDates {border-radius:16px;flex-shrink:0}
            .pair-loading .workspace,
            .pair-loading .v04-kpis,
            .pair-loading .utilities {
                pointer-events:none;opacity:.65;
            }
            @media print {
                #localDatePanel button,
                #localDatePanel label,
                #pairSources,#dataInfo {display:none}
                #localDatePanel {max-height:none;overflow:visible}
            }
        `;
        document.head.appendChild(style);

        const apply = make('button', 'Apply');
        apply.id = 'applyDates';
        apply.type = 'button';
        apply.onclick = applyDates;
        document.querySelector('header .dates').appendChild(apply);

        const panel = make('section');
        panel.id = 'localDatePanel';
        panel.setAttribute(
            'aria-label', 'Archived date selection and status'
        );

        for (const [role, title] of [
            ['current', 'Current version'],
            ['prior', 'Prior version']
        ]) {
            const label = make('label', title);
            const select = make('select');

            select.id = role + 'Version';
            select.setAttribute('aria-label', title);
            select.onchange = showStatus;

            label.hidden = true;
            label.appendChild(select);
            panel.appendChild(label);

            // Remove the original immediate date-change behavior.
            $(role).onchange = () => {
                fillVersions(role);
                showStatus();
            };
        }

        const status = make('span');
        status.id = 'pairStatus';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        panel.appendChild(status);
        const dataInfo = make('details');
        dataInfo.id = 'dataInfo';
        const dataSummary = make('summary', 'Data info');
        dataSummary.id = 'dataInfoSummary';
        dataInfo.appendChild(dataSummary);
        const dataBody = make('div');
        dataBody.id = 'dataInfoBody';
        dataInfo.appendChild(dataBody);
        const review = make('button', 'Review sources');
        review.id = 'reviewSources'; review.type = 'button';
        review.onclick = () => { reviewing = !reviewing; for (const role of ['current','prior']) fillVersions(role); dataInfo.open = reviewing || needsReview(); showStatus(); };
        dataBody.appendChild(review);
        const save = make('button', 'Save reviewed sources');
        save.id = 'saveSources'; save.type = 'button'; save.onclick = saveSources; dataBody.appendChild(save);
        const refresh = make('button', 'Refresh dates');
        refresh.id = 'refreshDates'; refresh.type = 'button'; refresh.onclick = refreshDates; dataBody.appendChild(refresh);
        const download = make('button', 'Download timing');
        download.id = 'downloadTiming'; download.type = 'button'; download.onclick = downloadTiming; dataBody.appendChild(download);
        for (const id of ['archiveStatus','pairTiming']) { const node=make('span'); node.id=id; dataBody.appendChild(node); }
        const sources = make('details'); sources.id = 'pairSources'; dataBody.appendChild(sources);
        panel.appendChild(dataInfo);

        const kpis = document.querySelector('.v04-kpis');
        if (kpis) kpis.after(panel);
        else document.querySelector('header').after(panel);

        // Prevent keyboard interaction with stale results during Apply.
        document.addEventListener('keydown', event => {
            if (
                busy &&
                event.target.closest(
                    '.workspace,.v04-kpis,.utilities'
                )
            ) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }

            if (
                (busy || refreshing || pending()) &&
                (event.ctrlKey || event.metaKey) &&
                event.key.toLowerCase() === 'p'
            ) {
                event.preventDefault();
                $('pairStatus').textContent =
                    'Apply the requested dates before printing.';
            }
        }, true);

        hideRawPopulationControl();
        renderSources();
        refreshDates();
    }

    if (document.readyState === 'loading') {
        document.addEventListener(
            'DOMContentLoaded',
            () => requestAnimationFrame(start)
        );
    } else {
        requestAnimationFrame(start);
    }
})();
"""


def load_manager():
    path = ROOT / "snapshot_manager.py"

    if not path.is_file():
        raise ValueError(
            "Put local_date_app.py beside snapshot_manager.py."
        )

    spec = importlib.util.spec_from_file_location(
        "commercial_mtm_snapshot_manager", path
    )

    if spec is None or spec.loader is None:
        raise ValueError("Could not load snapshot_manager.py.")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    required = [
        "Archive",
        "iso",
        "resolve_version",
        "pair_payload",
        "COLUMNS",
    ]

    missing = [
        name for name in required
        if not hasattr(module, name)
    ]

    if missing:
        raise ValueError(
            "Snapshot manager interface missing: "
            + ", ".join(missing)
        )

    return module


def build_served_core():
    source = (WORKSPACE / "workspace.js").read_text(
        encoding="utf-8-sig"
    )

    marker = "window.PNL_APP={state:S,"

    if source.count(marker) != 1:
        raise ValueError(
            "workspace.js differs from the supplied version: "
            "expected one PNL_APP state export. "
            "Original files were not changed."
        )

    required_markers = [
        "const D=window.PNL_DATA",
        "function aggregate()",
        "function schedule()",
        "const notes=document.createElement('p')",
    ]

    for item in required_markers:
        if item not in source:
            raise ValueError(
                "Unsupported workspace.js interface: " + item
            )

    return source.replace(
        marker,
        CORE_EXTENSION
        + "\nwindow.PNL_APP={replaceData,state:S,",
        1,
    ).encode("utf-8")


def build_served_html():
    source = (WORKSPACE / PAGE_NAME).read_text(
        encoding="utf-8-sig"
    )

    if not re.search(r"</body\s*>", source, re.IGNORECASE):
        raise ValueError("Dashboard HTML has no closing body tag.")

    if 'id="local-date-controls"' in source:
        raise ValueError(
            "The workspace HTML already contains local-date-controls. "
            "Use the original workspace HTML with this application."
        )

    return re.sub(
        r"</body\s*>",
        lambda match:
            '\n<script id="local-date-controls" '
            'src="/local-controls.js"></script>\n'
            + match.group(),
        source,
        count=1,
        flags=re.IGNORECASE,
    ).encode("utf-8")


def load_selections():
    path = ROOT / "local_date_selections.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("format") != 1
            or not isinstance(data.get("dates"), dict)):
        raise ValueError("Invalid saved source selections; review the selections file.")
    for day, item in data["dates"].items():
        if (not isinstance(day, str) or not isinstance(item, dict)
                or not isinstance(item.get("version"), str)
                or not item["version"]):
            raise ValueError("Invalid saved source selection.")
    return data["dates"]


def save_selections(record):
    if not isinstance(record, dict) or set(record) != {"dates"}:
        raise ValueError("Expected reviewed date/version selections.")
    choices = record["dates"]
    if not isinstance(choices, dict) or not 1 <= len(choices) <= 2:
        raise ValueError("Review one or two dates at a time.")
    archive = MANAGER.Archive(ROOT)
    with archive.exclusive():
        catalog = archive.load()
        for day, version in choices.items():
            if (not isinstance(day, str) or MANAGER.iso(day) != day
                    or not isinstance(version, str) or not version
                    or version not in catalog["snapshots"].get(day, {})):
                raise ValueError("Reviewed source is not available in the archive.")
            MANAGER.resolve_version(catalog, day, version)
        with SELECTION_LOCK:
            saved = load_selections()
            for day, version in choices.items():
                saved[day] = {"version": version, "reviewedUtc": utc_now()}
            path = ROOT / "local_date_selections.json"
            temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
            try:
                with temporary.open("x", encoding="utf-8") as output:
                    json.dump({"format": 1, "dates": saved}, output, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    return {"saved": True}


def get_catalog():
    archive = MANAGER.Archive(ROOT)
    catalog = archive.load()
    dates = {}

    for day, versions in sorted(catalog["snapshots"].items()):
        dates[day] = []

        for version, item in versions.items():
            files = [
                catalog["sources"][source_hash]["fileName"]
                for source_hash in item["sources"]
            ]

            dates[day].append({
                "version": version,
                "rows": item["rows"],
                "files": files,
            })

    import_log = archive.path / "last_import.json"

    if import_log.is_file():
        last_import = json.loads(
            import_log.read_text(encoding="utf-8")
        )
    else:
        last_import = {}

    return {
        "dates": dates,
        "savedSelections": load_selections(),
        "lastImportFinished": last_import.get("finishedUtc"),
        "lastImportStatus": last_import.get("status"),
    }


def one_parameter(query, key):
    values = query.get(key)

    if not values or len(values) != 1 or not values[0]:
        raise ValueError(
            "Exactly one nonempty parameter is required: " + key
        )

    return values[0]


def prepare_pair(query):
    current_date = one_parameter(query, "current")
    prior_date = one_parameter(query, "prior")
    current_version = one_parameter(query, "currentVersion")
    prior_version = one_parameter(query, "priorVersion")

    if (
        MANAGER.iso(current_date) != current_date
        or MANAGER.iso(prior_date) != prior_date
        or current_date <= prior_date
    ):
        raise ValueError(
            "Current must be later than Prior. "
            "Use available YYYY-MM-DD valuation dates."
        )

    archive = MANAGER.Archive(ROOT)

    with archive.exclusive():
        catalog = archive.load()

        saved = load_selections()
        for day, version in ((current_date, current_version), (prior_date, prior_version)):
            if (saved.get(day, {}).get("version") != version
                    or version not in catalog["snapshots"].get(day, {})):
                raise ValueError("Source review required for " + day + ". Refresh dates and save a reviewed source.")
        current = MANAGER.resolve_version(
            catalog, current_date, current_version
        )
        prior = MANAGER.resolve_version(
            catalog, prior_date, prior_version
        )

        if (
            current["columns"] != MANAGER.COLUMNS
            or prior["columns"] != MANAGER.COLUMNS
        ):
            raise ValueError(
                "Selected snapshots have an unsupported column schema."
            )

        if current["schemaHash"] != prior["schemaHash"]:
            raise ValueError(
                "Selected snapshots have different source schemas "
                "or mappings. Mapping review is required."
            )

        # Existing manager checks payload hashes and financial controls.
        return MANAGER.pair_payload(
            archive, catalog, current, prior
        )


def save_metric(record):
    if not isinstance(record, dict):
        raise ValueError("Timing record must be a JSON object.")

    result = {"loggedUtc": utc_now()}

    text_fields = [
        "observedUtc",
        "current",
        "prior",
        "currentVersion",
        "priorVersion",
    ]

    numeric_fields = [
        "serverPrepareMs",
        "requestAndBodyMs",
        "parseMs",
        "calculationMs",
        "visualSettleMs",
        "totalApplyMs",
        "records",
    ]

    for key in text_fields:
        value = record.get(key)

        if not isinstance(value, str) or len(value) > 160:
            raise ValueError("Invalid timing field: " + key)

        result[key] = value

    for key in numeric_fields:
        value = record.get(key)

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("Invalid timing field: " + key)

        result[key] = value

    if not isinstance(record.get("visualsConfirmed"), bool):
        raise ValueError("Invalid visualsConfirmed field.")

    result["visualsConfirmed"] = record["visualsConfirmed"]

    with LOG_LOCK:
        directory = ROOT / "local_date_logs"
        directory.mkdir(exist_ok=True)

        with (directory / "apply_timings.jsonl").open(
            "a", encoding="utf-8"
        ) as output:
            output.write(
                json.dumps(
                    result,
                    ensure_ascii=True,
                    allow_nan=False,
                )
                + "\n"
            )


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    server_version = "CommercialMTMLocal/0.7-ui-cleanup"

    def setup(self):
        super().setup()
        self.connection.settimeout(120)

    def log_message(self, format_string, *args):
        # Do not log bootstrap tokens or query parameters.
        print(
            "[{}] {}".format(
                datetime.now().strftime("%H:%M:%S"),
                self.command,
            ),
            flush=True,
        )

    def valid_host(self):
        expected = "127.0.0.1:" + str(self.server.server_port)
        return self.headers.get("Host", "") == expected

    def valid_session(self):
        try:
            cookies = SimpleCookie()
            cookies.load(self.headers.get("Cookie", ""))
            item = cookies.get(COOKIE_NAME)

            return (
                item is not None
                and secrets.compare_digest(
                    item.value, SESSION_TOKEN
                )
            )
        except Exception:
            return False

    def valid_origin(self):
        expected = (
            "http://127.0.0.1:"
            + str(self.server.server_port)
        )

        origin = self.headers.get("Origin")
        return origin is None or origin == expected

    def send_bytes(
        self,
        status,
        content,
        content_type,
        extra_headers=None,
        compress=False,
    ):
        body = content
        compressed = False

        if (
            compress
            and len(body) > 4096
            and "gzip" in self.headers.get("Accept-Encoding", "")
        ):
            body = gzip.compress(body, compresslevel=1)
            compressed = True

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'",
        )

        if compressed:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")

        for key, value in (extra_headers or {}).items():
            self.send_header(key, str(value))

        self.end_headers()

        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, status, value, extra_headers=None):
        self.send_bytes(
            status,
            encode_json(value),
            "application/json; charset=utf-8",
            extra_headers=extra_headers,
        )

    def authorize(self):
        if not self.valid_host():
            self.send_json(403, {
                "error": "Unexpected Host header."
            })
            return False

        if not self.valid_session():
            self.send_json(403, {
                "error":
                    "Local session missing. Reopen using the launch "
                    "address printed in the command window."
            })
            return False

        if not self.valid_origin():
            self.send_json(403, {
                "error": "Cross-origin requests are not allowed."
            })
            return False

        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.send_json(403, {
                "error": "Cross-site requests are not allowed."
            })
            return False

        return True

    def do_GET(self):
        parsed = urlsplit(self.path)

        if not self.valid_host():
            self.send_json(403, {
                "error": "Unexpected Host header."
            })
            return

        if parsed.path.startswith("/start/"):
            supplied = parsed.path[len("/start/"):]

            if not secrets.compare_digest(
                supplied, SESSION_TOKEN
            ):
                self.send_json(403, {
                    "error": "Invalid local session token."
                })
                return

            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header(
                "Set-Cookie",
                COOKIE_NAME + "=" + SESSION_TOKEN
                + "; Path=/; HttpOnly; SameSite=Strict",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        if not self.authorize():
            return

        try:
            if parsed.path in (
                "/", "/index.html", "/index_v0_4.html"
            ):
                self.send_bytes(
                    200,
                    build_served_html(),
                    "text/html; charset=utf-8",
                    compress=True,
                )
                return

            if parsed.path == "/workspace.js":
                self.send_bytes(
                    200,
                    PATCHED_CORE,
                    "application/javascript; charset=utf-8",
                    compress=True,
                )
                return

            if parsed.path == "/local-controls.js":
                self.send_bytes(
                    200,
                    CLIENT_JS.encode("utf-8"),
                    "application/javascript; charset=utf-8",
                    compress=True,
                )
                return

            # Explicit allowlist. No directory listing or arbitrary
            # source/archive file access is exposed.
            static_files = {
                "/workspace.css": (
                    "workspace.css",
                    "text/css; charset=utf-8",
                ),
                "/xlsx_export.js": (
                    "xlsx_export.js",
                    "application/javascript; charset=utf-8",
                ),
                "/data.js": (
                    "data.js",
                    "application/javascript; charset=utf-8",
                ),
            }

            if parsed.path in static_files:
                filename, content_type = static_files[parsed.path]

                self.send_bytes(
                    200,
                    (WORKSPACE / filename).read_bytes(),
                    content_type,
                    compress=True,
                )
                return

            if parsed.path == "/api/catalog":
                self.send_json(200, get_catalog())
                return

            if parsed.path == "/api/pair":
                if not PAIR_LOCK.acquire(blocking=False):
                    self.send_json(409, {
                        "error":
                            "Another pair request is running. "
                            "Try Apply again after it finishes."
                    })
                    return

                try:
                    started = time.perf_counter()

                    query = parse_qs(
                        parsed.query,
                        keep_blank_values=True,
                        max_num_fields=8,
                    )

                    payload = prepare_pair(query)
                    content = encode_json(payload)

                    elapsed_ms = (
                        time.perf_counter() - started
                    ) * 1000

                    self.send_bytes(
                        200,
                        content,
                        "application/json; charset=utf-8",
                        extra_headers={
                            "X-Prepare-Ms": format(
                                elapsed_ms, ".3f"
                            )
                        },
                        compress=True,
                    )

                finally:
                    PAIR_LOCK.release()

                return

            if parsed.path == "/favicon.ico":
                self.send_bytes(204, b"", "image/x-icon")
                return

            self.send_json(404, {
                "error": "Resource not available."
            })

        except (
            ValueError,
            KeyError,
            FileNotFoundError,
        ) as error:
            self.send_json(400, {
                "error": str(error)
            })

        except Exception as error:
            print(
                "Local application error:",
                type(error).__name__,
                str(error),
                flush=True,
            )

            self.send_json(500, {
                "error":
                    "Request failed. Review the command-window "
                    "message."
            })

    def do_POST(self):
        if not self.authorize():
            return

        route = urlsplit(self.path).path
        if route not in ("/api/metrics", "/api/selections"):
            self.send_json(404, {
                "error": "Resource not available."
            })
            return

        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError(
                    "Transfer-Encoding is not supported."
                )

            length = int(
                self.headers.get("Content-Length", "0")
            )

            if length <= 0 or length > 16384:
                raise ValueError(
                    "Invalid timing-record body length."
                )

            content_type = self.headers.get(
                "Content-Type", ""
            ).split(";")[0].strip().lower()

            if content_type != "application/json":
                raise ValueError(
                    "Expected an application/json timing record."
                )

            record = json.loads(
                self.rfile.read(length).decode("utf-8")
            )

            if route == "/api/selections":
                self.send_json(200, save_selections(record))
            else:
                save_metric(record)
                self.send_json(200, {"saved": True})

        except (ValueError, UnicodeDecodeError) as error:
            self.send_json(400, {
                "error": str(error)
            })

        except Exception as error:
            print(
                "Timing-log error:", str(error), flush=True
            )

            self.send_json(500, {
                "error": "Record could not be saved. Review the command window."
            })


def preflight():
    global MANAGER, PATCHED_CORE, PAGE_NAME

    if not WORKSPACE.is_dir():
        raise ValueError(
            "The workspace folder was not found beside this script."
        )

    if (WORKSPACE / "index_v0_4.html").is_file():
        PAGE_NAME = "index_v0_4.html"
    elif (WORKSPACE / "index.html").is_file():
        PAGE_NAME = "index.html"
    else:
        raise ValueError(
            "No index_v0_4.html or index.html in workspace."
        )

    for filename in [
        "workspace.js",
        "workspace.css",
        "xlsx_export.js",
        "data.js",
    ]:
        if not (WORKSPACE / filename).is_file():
            raise ValueError(
                "Required workspace file missing: " + filename
            )

    catalog_path = ROOT / "snapshot_archive" / "catalog.json"

    if not catalog_path.is_file():
        raise ValueError(
            "Snapshot catalog missing. "
            "Run IMPORT_SNAPSHOTS.cmd first."
        )

    MANAGER = load_manager()
    PATCHED_CORE = build_served_core()

    build_served_html()
    catalog = get_catalog()

    if len(catalog["dates"]) < 2:
        raise ValueError(
            "At least two archived valuation dates are required."
        )

    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check required files and interfaces, then exit.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Default 0 chooses an available local port.",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the launch address without opening a browser.",
    )

    args = parser.parse_args()

    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535.")

    try:
        catalog = preflight()

        print(
            "Preflight passed. Archived dates:",
            ", ".join(sorted(catalog["dates"])),
            flush=True,
        )

        if args.check:
            print(
                "No server started. Original dashboard files "
                "were not changed.",
                flush=True,
            )
            return 0

        server = LocalServer(
            ("127.0.0.1", args.port),
            Handler,
        )

        address = (
            "http://127.0.0.1:"
            + str(server.server_port)
            + "/start/"
            + SESSION_TOKEN
        )

        print()
        print("Commercial MTM local date-comparison prototype")
        print("Local computer only. Not a shared dashboard.")
        print()
        print("Launch address:")
        print(address)
        print()
        print("Keep this command window open while using the app.")
        print("Press Ctrl+C here to stop.")
        print()
        print("Initial results come from workspace/data.js.")
        print("Select dates and Apply to load an archived pair.")
        print(
            "After importing new snapshots, select Refresh dates."
        )
        print()

        if not args.no_browser:
            webbrowser.open(address)

        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            print("\nStopping local application.", flush=True)
        finally:
            server.server_close()

        return 0

    except Exception as error:
        print("STOPPED:", str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())