#!/usr/bin/env python3
"""Add a new v0.4 presentation page to an existing v0.3 workspace.
Only new files are written. Existing data, scripts, source files and HTML are not edited.
No dependencies, workbook reads, package installation, or network calls.
"""
import argparse,hashlib,json,re,sys,webbrowser
from datetime import datetime,timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def locate(project):
    base=Path(project).expanduser().resolve() if project else HERE
    candidates=[base/'workspace',base,base.parent/'workspace']
    for p in candidates:
        if all((p/n).is_file() for n in ('index.html','workspace.js','workspace.css','data.js','xlsx_export.js')):
            return p
    raise FileNotFoundError('Existing v0.3 workspace not found. Extract these patch files into the SAME main folder that contains OPEN_WORKSPACE.cmd and the workspace folder. Do not put them inside comparison_data.')

def apply(project=None,open_page=False):
    workspace=locate(project);original=workspace/'index.html';html=original.read_text(encoding='utf-8-sig');core=(workspace/'workspace.js').read_text(encoding='utf-8-sig')
    needed=['measure','mode','rail','matrix','body','head','foot','chips','depth','side','period','units','zero','sort','labelWidth','rowSearch','focusPath','slicers','moreSlicers','resetFilters','railToggle']
    missing=[i for i in needed if ('id='+chr(34)+i+chr(34)) not in html and ('id='+chr(39)+i+chr(39)) not in html]
    if missing:raise ValueError('This patch requires the v0.3 workspace. Missing UI anchors: '+', '.join(missing))
    if 'PNL_APP' not in core or 'ActivityBucket' not in core:raise ValueError('The expected v0.3 eight-level application interface was not found. No files changed.')
    # Protect every existing file in the published workspace except prior patch outputs.
    protected=[p for p in workspace.iterdir() if p.is_file() and p.name not in ('index_v0_4.html','visual_patch_manifest.json')]
    before={p.name:sha(p) for p in protected}
    css=(HERE/'visual_v04.css').read_text(encoding='utf-8');js=(HERE/'visual_v04.js').read_text(encoding='utf-8');logo=(HERE/'logo_uri.txt').read_text(encoding='ascii').strip()
    if not logo.startswith('data:image/png;base64,'):raise ValueError('Logo asset is missing or invalid')
    js=js.replace('__LOGO_URI__',logo)
    if '</style' in css.lower() or '</script' in js.lower():raise ValueError('Unexpected HTML terminator in visual resources')
    if not re.search(r'</head\s*>',html,re.I) or not re.search(r'</body\s*>',html,re.I):raise ValueError('The original HTML structure is incomplete')
    styled=re.sub(r'</head\s*>',lambda m:'\n<!-- v0.4 visual layer; original data and scripts retained -->\n<style id="pnl-v04-style">\n'+css+'\n</style>\n'+m.group(),html,count=1,flags=re.I)
    styled=re.sub(r'</body\s*>',lambda m:'\n<script id="pnl-v04-adapter">\n'+js+'\n</script>\n'+m.group(),styled,count=1,flags=re.I)
    target=workspace/'index_v0_4.html';target.write_text(styled,encoding='utf-8')
    after={p.name:sha(p) for p in protected}
    if before!=after:
        target.unlink(missing_ok=True)
        raise RuntimeError('An existing workspace file changed while applying the patch. New page removed. Retry when no rebuild is running.')
    report={'visualVersion':'0.4.0','appliedUtc':datetime.now(timezone.utc).isoformat(),'originalPage':str(original),'newPage':str(target),'dataAndCoreUnchanged':True,'protectedFiles':{k:{'before':v,'after':after[k]} for k,v in before.items()},'scope':'Presentation only. No hierarchy, slicer, filter default, date, preset, period mapping, data, or financial-calculation changes.'}
    (workspace/'visual_patch_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    launcher=workspace.parent/'OPEN_REDESIGNED.cmd'
    launcher.write_text('@echo off\r\nsetlocal\r\nstart "" "%~dp0workspace\\index_v0_4.html"\r\n',encoding='ascii')
    print('SUCCESS: visual redesign applied. Existing data and core scripts are unchanged.')
    print('Open: '+str(target));print('Original view remains available: '+str(original))
    if open_page:webbrowser.open(target.as_uri())
    return target

def main():
    ap=argparse.ArgumentParser(description='Apply a visual-only v0.4 layer to the existing v0.3 workspace.');ap.add_argument('--project',help='Existing project folder or workspace folder');ap.add_argument('--open',action='store_true');a=ap.parse_args()
    try:apply(a.project,a.open)
    except Exception as exc:print('NOT APPLIED: '+str(exc),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
