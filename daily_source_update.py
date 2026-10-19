"""Daily-source launcher and visible period-reset patch for existing v0.3/v0.4.
No source-workbook writes, no nightly fallback, no changes to calculation scripts.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,time,webbrowser,zipfile
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
CONFIG=HERE/'daily_source_config.json'
RESET_JS=r'''(()=>{'use strict';function install(){const original=document.getElementById('periodCollapse');if(!original)return;const toolbar=document.querySelector('.v04-toolbar')||document.querySelector('.matrix-tools');if(!toolbar||document.getElementById('dailyColumnReset'))return;const button=document.createElement('button');button.id='dailyColumnReset';button.type='button';button.textContent='Reset columns';button.title='Collapse delivery-period columns to Year2 buckets. Preserve row expansion, filters, dates, measure, units, and view.';button.setAttribute('aria-label',button.title);button.style.cssText='white-space:nowrap;flex-shrink:0;font-size:11px;min-height:30px;border:1px solid var(--line-strong,#C3CCD7);border-radius:5px;padding:4px 9px;background:var(--surface,#FFFFFF);color:var(--navy-600,#1F5FA8)';button.onclick=()=>original.click();const options=toolbar.querySelector('.v04-options');if(options)options.before(button);else toolbar.appendChild(button);}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>requestAnimationFrame(install));else requestAnimationFrame(install);})();'''

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def root_at(path):
 p=Path(path).resolve() if path else HERE
 if p.name=='workspace' and (p.parent/'build_workspace.py').is_file():p=p.parent
 if not (p/'build_workspace.py').is_file() or not (p/'workspace').is_dir():raise ValueError('Put these patch files beside build_workspace.py and the existing workspace folder.')
 return p

def add_reset(root):
 protected=[p for p in (root/'workspace').iterdir() if p.is_file() and p.suffix not in ('.html',)]
 before={p.name:digest(p) for p in protected}
 changed=[];compatible=0
 for folder in [root,root/'workspace']:
  for name in ['index.html','index_v0_4.html']:
   p=folder/name
   if not p.is_file():continue
   text=p.read_text(encoding='utf-8-sig')
   if 'id="daily-column-reset-adapter"' in text:compatible+=1;continue
   if 'id="periodCollapse"' not in text and "id='periodCollapse'" not in text:continue
   if '</body>' not in text.lower():continue
   compatible+=1
   backup=p.with_name(p.name+'.before_daily_patch')
   if not backup.exists():shutil.copy2(p,backup)
   import re
   updated=re.sub(r'</body\s*>',lambda m:'\n<script id="daily-column-reset-adapter">'+RESET_JS+'</script>\n'+m.group(),text,count=1,flags=re.I)
   p.write_text(updated,encoding='utf-8');changed.append(str(p))
 if not compatible:raise ValueError('No compatible periodCollapse control found. No column-reset button was installed.')
 after={p.name:digest(p) for p in protected}
 if before!=after:raise RuntimeError('A protected data/core file changed concurrently. Stop other builds and retry.')
 report={'appliedUtc':datetime.now(timezone.utc).isoformat(),'updatedPages':changed,'dataAndCoreUnchanged':before==after,'protectedHashes':before}
 (root/'daily_patch_manifest.json').write_text(json.dumps(report,indent=2))
 print('Reset columns adapter installed. Data and core scripts unchanged.')
 return report

def pick_folder():
 import tkinter as tk
 from tkinter import filedialog
 app=tk.Tk();app.withdraw();app.attributes('-topmost',True)
 folder=filedialog.askdirectory(title='Select the Commercial MTM daily-file folder (not the nightly RISK folder)',parent=app)
 app.destroy()
 if not folder:raise ValueError('Folder selection cancelled; nothing changed.')
 return Path(folder)

def validate_folder(p):
 p=p.resolve()
 if not p.is_dir():raise ValueError('Configured daily folder is unavailable: '+str(p))
 normalized=str(p).replace('\\','/').lower()
 if '/endur/autofiles/risk' in normalized:raise ValueError('Nightly RISK folder is intentionally disallowed. Select the Commercial MTM published daily folder.')
 return p

def configure(folder=None):
 p=validate_folder(Path(folder) if folder else pick_folder())
 CONFIG.write_text(json.dumps({'dailyFolder':str(p),'pattern':'*TPORT_MTM_COMMERCIAL*.xlsb','selection':'Explicit file selection if multiple candidates; no latest-modified guess','nightlyFallback':False},indent=2))
 print('Daily source folder saved: '+str(p));return p

def select_source(folder,explicit=None):
 candidates=sorted(p for p in folder.glob('*TPORT_MTM_COMMERCIAL*.xlsb') if p.is_file() and not p.name.startswith('~$'))
 if explicit:
  p=Path(explicit).resolve()
  if p.parent!=folder or p not in candidates:raise ValueError('Explicit source must be a matching XLSB directly inside the configured daily folder.')
  return p
 if not candidates:raise ValueError('No *TPORT_MTM_COMMERCIAL*.xlsb files found directly in the daily folder. No nightly fallback attempted.')
 if len(candidates)==1:return candidates[0]
 import tkinter as tk
 from tkinter import filedialog
 app=tk.Tk();app.withdraw();app.attributes('-topmost',True)
 selected=filedialog.askopenfilename(title='Select the published DAILY workbook; multiple files found',initialdir=str(folder),filetypes=[('Commercial MTM binary workbooks','*TPORT_MTM_COMMERCIAL*.xlsb')],parent=app);app.destroy()
 if not selected:raise ValueError('Daily file selection cancelled. Existing dashboard unchanged.')
 return select_source(folder,selected)

def build_daily(root,source=None):
 if not CONFIG.exists():configure()
 cfg=json.loads(CONFIG.read_text());folder=validate_folder(Path(cfg['dailyFolder']));src=select_source(folder,source)
 target=root/'workspace';builder=root/'build_workspace.py';timing={'startedUtc':datetime.now(timezone.utc).isoformat(),'source':str(src),'folder':str(folder),'status':'FAILED'};start=time.perf_counter()
 try:
  with tempfile.TemporaryDirectory(prefix='pnl_daily_') as td:
   tmp=Path(td);copy=tmp/src.name;stat=src.stat();t=time.perf_counter();shutil.copy2(src,copy);now=src.stat()
   if (stat.st_size,stat.st_mtime_ns)!=(now.st_size,now.st_mtime_ns):raise ValueError('Daily file changed while copying. Existing dashboard retained. Retry after the publishing process completes.')
   if copy.stat().st_size!=stat.st_size:raise ValueError('Daily copy is incomplete.')
   timing['sourceCopySeconds']=time.perf_counter()-t
   # Container integrity check, not a workbook refresh or recalculation.
   with zipfile.ZipFile(copy) as z:
    if 'xl/workbook.bin' not in z.namelist():raise ValueError('Selected file is not an XLSB workbook.')
    bad=z.testzip()
    if bad:raise ValueError('Incomplete or damaged workbook container: '+bad)
   out=tmp/'published';t=time.perf_counter()
   print('Selected daily file: '+str(src),flush=True)
   print('Reading a local read-only copy; source workbook will not be modified.',flush=True)
   subprocess.run([sys.executable,str(builder),'--file',str(copy),'--out',str(out)],check=True,cwd=str(root))
   timing['extractAndPublishSeconds']=time.perf_counter()-t
   required=['data.js','build_report.json','index.html','workspace.js','workspace.css','xlsx_export.js']
   if any(not (out/n).is_file() for n in required):raise ValueError('Existing builder did not produce the expected complete workspace. Nothing published.')
   report=json.loads((out/'build_report.json').read_text(encoding='utf-8-sig'));dates=report.get('dates',[])
   if not all(isinstance(d,str) and len(d)==10 for d in dates):raise ValueError('Invalid valuation-date list in build report.')
   if len(set(dates))<2:raise ValueError('Build report does not contain two validated valuation dates. Existing dashboard retained.')
   old_report=target/'build_report.json'
   if old_report.exists():
    old_dates=json.loads(old_report.read_text(encoding='utf-8-sig')).get('dates',[])
    if old_dates and max(dates)<max(old_dates):raise ValueError('Selected daily file would move the dashboard backwards to an older valuation date. Existing dashboard retained.')
    if old_dates and max(dates)==max(old_dates):print('NOTICE: latest valuation date is unchanged. This may be a same-date republication; no claim of freshness is made.',flush=True)
   timing['valuationDates']=dates;timing['sourceSha256']=digest(copy);timing['sourceSizeBytes']=stat.st_size
   print('Valuation dates inside the selected daily workbook: '+', '.join(dates),flush=True)
   # Keep all installed UI/core assets and v0.4 styling. Publish data only.
   payloads=['build_report.json','source_records.csv.gz','data.js']
   staged=[]
   for name in payloads:
    if (out/name).is_file():
     dest=target/(name+'.daily_pending');shutil.copy2(out/name,dest);staged.append((name,dest))
   for name,dest in staged:os.replace(dest,target/name)
   add_reset(root)
   timing['status']='SUCCESS'
 except Exception as e:
  timing['error']=str(e);raise
 finally:
  timing['totalSeconds']=time.perf_counter()-start
  (root/'daily_build_timing.json').write_text(json.dumps(timing,indent=2))
 print('Daily data published. Original calculation and visual scripts retained.')
 page=target/('index_v0_4.html' if (target/'index_v0_4.html').exists() else 'index.html')
 webbrowser.open(page.as_uri())

def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['install','configure','build']);ap.add_argument('--project');ap.add_argument('--folder');ap.add_argument('--source-file');a=ap.parse_args()
 try:
  root=root_at(a.project)
  if a.action=='install':add_reset(root)
  elif a.action=='configure':configure(a.folder)
  else:build_daily(root,a.source_file)
 except Exception as e:print('STOPPED: '+str(e),file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
