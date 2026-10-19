#!/usr/bin/env python3
"""Commercial MTM snapshot archive and pair publisher. Read-only XLSB input.
Python standard library + existing pyxlsb; optional python-calamine reader.
No server, no source macros, no changes to existing dashboard core or data.
"""
import argparse,contextlib,csv,gzip,hashlib,json,math,os,re,shutil,sys,tempfile,time,uuid,webbrowser,zipfile
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
VERSION='0.5.0'
HERE=Path(__file__).resolve().parent
FIELDS=[('ActivityBucket','Activity Bucket'),('Region','Region'),('AMA','AMA or Non-AMA'),('Strategy','Revised Strategy'),('DealType','DEALTYPE'),('Curve','Abbrev_Val_Pool'),('Counterparty','EXTBUNIT'),('DealID','DEALID'),('Year2',('Year2','Year Group')),('Year','Year'),('ContractMonth','ContractMonth'),('GeoRegion','GeoRegion'),('TradeMonth','Trade Month'),('SeasonDetail','Season Detail'),('NewDealCurveShift','New Deal / C-Shift'),('ServiceType','SERVICETYPE'),('EncumberedTag','Encumbered Tag'),('FwdMonthIncl','Fwd_Month_Incl'),('ValidEconDealType','Valid Econ Deal Type'),('ReportingType','Reporting Type'),('InterruptCommTrans','Interrupt Comm-Trans?')]
COLUMNS=['Date']+[k for k,_ in FIELDS]+['MTM','Fee']
REQUIRED=[k for k,_ in FIELDS[:11]]+['Date','MTM','Fee']
POLICY='raw-source-v1;last-Region;Year2-fallback-YearGroup;no-exclusions;no-dedup;no-FX;no-attribution'

def utc():return datetime.now(timezone.utc).isoformat()
def dump(x):return json.dumps(x,ensure_ascii=True,separators=(',',':'),allow_nan=False)
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def atomic_json(p,obj):
 tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  with tmp.open('w',encoding='utf-8') as f:json.dump(obj,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
  os.replace(tmp,p)
 finally:tmp.unlink(missing_ok=True)
def project_at(path=None):
 p=Path(path).expanduser().resolve() if path else HERE
 if p.name=='workspace':p=p.parent
 if not (p/'workspace'/'index.html').is_file():raise ValueError('Put the package beside your existing workspace folder, or use --project with the main project folder.')
 return p
class Archive:
 def __init__(self,project):
  self.project=project;self.path=project/'snapshot_archive';self.path.mkdir(exist_ok=True);(self.path/'snapshots').mkdir(exist_ok=True)
  self.catalog=self.path/'catalog.json';self.lock=self.path/'archive.lock'
 def load(self):
  if not self.catalog.exists():return {'archiveVersion':1,'policy':POLICY,'snapshots':{},'sources':{},'createdUtc':utc()}
  c=json.loads(self.catalog.read_text(encoding='utf-8'))
  if c.get('archiveVersion')!=1 or c.get('policy')!=POLICY:raise ValueError('Archive schema/policy mismatch. No automatic migration is allowed.')
  return c
 @contextlib.contextmanager
 def exclusive(self):
  try:fd=os.open(str(self.lock),os.O_CREAT|os.O_EXCL|os.O_WRONLY)
  except FileExistsError:raise ValueError('Archive is in use (archive.lock exists). Do not run concurrent imports/publishers. If a previous run crashed, verify it has ended before removing the lock.')
  try:
   os.write(fd,dump({'pid':os.getpid(),'startedUtc':utc()}).encode());os.close(fd);yield
  finally:self.lock.unlink(missing_ok=True)
 def resolve(self,relative):
  p=(self.path/relative).resolve()
  if not p.is_relative_to(self.path.resolve()):raise ValueError('Invalid archive path')
  return p

def iso(v,month=False):
 if v is None or v=='':return '(Blank)' if month else ''
 if isinstance(v,datetime):d=v.date()
 elif isinstance(v,date):d=v
 elif isinstance(v,(float,int)) and not isinstance(v,bool):
  if not math.isfinite(v):raise ValueError('Non-finite date')
  d=(datetime(1899,12,30)+timedelta(days=v)).date()
 else:
  t=str(v).strip();d=None
  for fmt in ('%Y-%m-%d','%m/%d/%Y','%m-%d-%Y','%Y-%m-%d %H:%M:%S','%b-%Y','%Y%m'):
   try:d=datetime.strptime(t,fmt).date();break
   except ValueError:pass
  if d is None:raise ValueError('Unrecognized date '+t)
 if not 1900<=d.year<=2200:raise ValueError('Date outside supported range')
 return (d.replace(day=1) if month else d).isoformat()
def text(v):
 if v is None or v=='':return '(Blank)'
 if isinstance(v,(date,datetime)):return v.isoformat()[:10]
 if isinstance(v,float):
  if not math.isfinite(v):raise ValueError('Non-finite source value')
  if v.is_integer():return str(int(v))
 return str(v).strip()
def raw_value(v):
 if isinstance(v,(date,datetime)):return {'isoDate':v.isoformat()}
 if isinstance(v,float) and not math.isfinite(v):raise ValueError('Non-finite raw source value')
 return v

def source_rows(path,reader):
 if reader=='calamine':
  from python_calamine import CalamineWorkbook
  w=CalamineWorkbook.from_path(str(path));yield from w.get_sheet_by_name('DPR_RiskAnalysis').iter_rows()
 else:
  try:from pyxlsb import open_workbook
  except ImportError:raise ValueError('pyxlsb is required. Use your existing Python environment, or install with: py -m pip install pyxlsb')
  with open_workbook(str(path)) as w,w.get_sheet('DPR_RiskAnalysis') as s:
   for row in s.rows():yield [c.v for c in row]

def mapping(headers):
 result={};notes=[];details={}
 for k,names in [('Date','EODDATE'),*FIELDS,('MTM','Economic Disc MTM'),('Fee','Disc Fee')]:
  for name in names if isinstance(names,tuple) else (names,):
   found=[i for i,h in enumerate(headers) if h==name]
   if found:
    result[k]=found[-1];details[k]={'source':name,'column':found[-1]+1}
    if len(found)>1:notes.append(name+': duplicate headers; last column selected, consistent with existing engine.')
    break
  if k in REQUIRED and k not in result:raise ValueError('Missing required field: '+k)
 if details['Year2']['source']!='Year2':notes.append('Year2 uses Year Group fallback; no historical bucket remapping is applied.')
 return result,details,notes

def extract(path,stage,reader):
 it=iter(source_rows(path,reader));headers=[str(x).strip() if x is not None else '' for x in next(it)];ix,details,notes=mapping(headers)
 streams={};stats={};skipped=0
 try:
  for rowno,r in enumerate(it,2):
   def v(k):
    i=ix.get(k);return r[i] if i is not None and i<len(r) else None
   if v('Date') in (None,''):skipped+=1;continue
   try:
    d=iso(v('Date'));values=[d]
    for k,_ in FIELDS:
     x=v(k)
     if k=='ContractMonth':x=iso(x,True)
     elif k=='TradeMonth' and isinstance(x,(date,datetime)):x=iso(x,True)
     elif k=='TradeMonth' and isinstance(x,(int,float)) and 20000<x<100000:x=iso(x,True)
     else:x=text(x)
     values.append(x)
    nums=[]
    for k in ('MTM','Fee'):
     x=v(k);n=0.0 if x in (None,'') else float(x)
     if not math.isfinite(n):raise ValueError('Non-finite '+k)
     nums.append(n)
    values.extend(nums)
    raw=[raw_value(x) for x in r]
    if d not in streams:
     streams[d]=gzip.open(stage/(d+'.jsonl.gz'),'wt',encoding='utf-8',newline='\n')
     stats[d]={'rows':0,'MTM':0.,'Fee':0.,'rowHashes':[],'financialHashes':[],'sourceFlags':Counter(),'blanks':Counter()}
    st=stats[d];st['rows']+=1;st['MTM']+=nums[0];st['Fee']+=nums[1]
    st['sourceFlags'][values[COLUMNS.index('NewDealCurveShift')]]+=1
    for k,x in zip(COLUMNS,values):
     if x=='(Blank)':st['blanks'][k]+=1
    # Full raw stored row content determines version. Duplicate rows retain multiplicity.
    st['rowHashes'].append(hashlib.sha256(dump(raw).encode()).digest())
    financial=[values[COLUMNS.index(k)] for k in ['Date','ActivityBucket','Region','AMA','Strategy','DealType','Curve','Counterparty','DealID','Year','ContractMonth','MTM','Fee']]
    st['financialHashes'].append(hashlib.sha256(dump(financial).encode()).digest())
    streams[d].write(dump({'sourceRow':rowno,'values':values,'raw':raw})+'\n')
   except Exception as e:raise ValueError('Source row '+str(rowno)+': '+str(e)) from e
   if sum(x['rows'] for x in stats.values())%25000==0:print('Read '+format(sum(x['rows'] for x in stats.values()),',')+' dated records',flush=True)
 finally:
  for f in streams.values():f.close()
 if not stats:raise ValueError('No dated source records')
 schema_hash=hashlib.sha256(dump({'headers':headers,'mapping':details,'policy':POLICY}).encode()).hexdigest()
 result={}
 for d,st in stats.items():
  content=hashlib.sha256(schema_hash.encode()+b''.join(sorted(st.pop('rowHashes')))).hexdigest()
  fin=hashlib.sha256(b''.join(sorted(st.pop('financialHashes')))).hexdigest()
  st['Total']=st['MTM']+st['Fee'];st['sourceFlags']=dict(st['sourceFlags']);st['blanks']=dict(st['blanks'])
  result[d]={**st,'date':d,'version':content,'financialFingerprint':fin,'schemaHash':schema_hash,'mapping':details,'warnings':notes,'missingOptionalFields':[k for k,_ in FIELDS if k not in ix],'headers':headers,'columns':COLUMNS}
 return result,skipped

def import_file(archive,path,reader='pyxlsb'):
 path=Path(path).resolve();validate_folder(path.parent);started=time.perf_counter();stat=path.stat()
 if path.suffix.lower()!='.xlsb' or path.name.startswith('~$'):raise ValueError('Expected a non-lock XLSB file')
 with tempfile.TemporaryDirectory(prefix='pnl_snapshot_') as td:
  stage=Path(td);copy=stage/path.name;t=time.perf_counter();shutil.copy2(path,copy);after=path.stat()
  if (stat.st_size,stat.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or copy.stat().st_size!=stat.st_size:raise ValueError('Source changed during copy; no snapshot imported')
  source_hash=sha(copy);copy_seconds=time.perf_counter()-t;catalog=archive.load()
  if source_hash in catalog['sources']:
   source=catalog['sources'][source_hash]
   # Verify referenced archive payloads before skipping an already-seen source.
   for ref in source['snapshots']:
    m=catalog['snapshots'][ref['date']][ref['version']];p=archive.resolve(m['payload'])
    if not p.is_file() or sha(p)!=m['payloadSha256']:raise ValueError('Cached payload missing or corrupt; no automatic replacement: '+str(p))
   source.setdefault('paths',[])
   if str(path) not in source['paths']:source['paths'].append(str(path))
   atomic_json(archive.catalog,catalog)
   return {'file':str(path),'status':'UNCHANGED_SOURCE','sourceSha256':source_hash,'seconds':time.perf_counter()-started,'snapshots':source['snapshots']}
  previous_readers={s.get('reader') for s in catalog['sources'].values()}
  if previous_readers and previous_readers!={reader}:raise ValueError('Use the same XLSB reader as the existing archive to avoid reader-format version differences: '+str(previous_readers))
  with zipfile.ZipFile(copy) as z:
   if 'xl/workbook.bin' not in z.namelist() or z.testzip():raise ValueError('Incomplete or invalid XLSB container')
  t=time.perf_counter();snapshots,skipped=extract(copy,stage,reader);extract_seconds=time.perf_counter()-t;refs=[]
  for d,m in snapshots.items():
   versions=catalog['snapshots'].setdefault(d,{});version=m['version'];ref={'date':d,'version':version};refs.append(ref)
   if version not in versions:
    relative='snapshots/'+d+'/'+version+'.jsonl.gz';dest=archive.resolve(relative);dest.parent.mkdir(exist_ok=True)
    # Content-addressed orphan from an interrupted earlier catalog commit can be safely replaced.
    pending=dest.with_name(dest.name+'.'+uuid.uuid4().hex+'.tmp');shutil.copy2(stage/(d+'.jsonl.gz'),pending);os.replace(pending,dest)
    versions[version]={**m,'payload':relative,'payloadSha256':sha(dest),'importedUtc':utc(),'payloadOriginSourceSha256':source_hash,'reader':reader,'sources':[]}
   if source_hash not in versions[version]['sources']:versions[version]['sources'].append(source_hash)
  catalog['sources'][source_hash]={'fileName':path.name,'paths':[str(path)],'sourceSha256':source_hash,'bytes':stat.st_size,'modifiedUtc':datetime.fromtimestamp(stat.st_mtime,timezone.utc).isoformat(),'importedUtc':utc(),'reader':reader,'skippedUndatedRows':skipped,'snapshots':refs}
  catalog['updatedUtc']=utc();atomic_json(archive.catalog,catalog)
  return {'file':str(path),'status':'IMPORTED','sourceSha256':source_hash,'copyAndHashSeconds':copy_seconds,'extractSeconds':extract_seconds,'seconds':time.perf_counter()-started,'snapshots':refs}

def validate_folder(folder):
 p=Path(folder).expanduser().resolve()
 if not p.is_dir():raise ValueError('Daily folder is unavailable: '+str(p))
 if '/endur/autofiles/risk' in str(p).replace('\\','/').lower():raise ValueError('Nightly RISK folder is disallowed; use the published Commercial MTM folder')
 return p

def choose_folder(project,explicit=None):
 if explicit:return validate_folder(explicit)
 cfg=project/'daily_source_config.json'
 if cfg.exists():return validate_folder(json.loads(cfg.read_text())['dailyFolder'])
 import tkinter as tk
 from tkinter import filedialog
 app=tk.Tk();app.withdraw();app.attributes('-topmost',True)
 try:p=filedialog.askdirectory(title='Select Commercial MTM daily-file folder',parent=app)
 finally:app.destroy()
 if not p:raise ValueError('Folder selection cancelled')
 p=validate_folder(p);atomic_json(cfg,{'dailyFolder':str(p),'pattern':'*TPORT_MTM_COMMERCIAL*.xlsb','nightlyFallback':False});return p

def run_import(project,folder=None,files=None,reader='pyxlsb',include_history=False):
 archive=Archive(project);paths=[Path(p).resolve() for p in files] if files else list(choose_folder(project,folder).glob('*TPORT_MTM_COMMERCIAL*.xlsb'))
 if not files and include_history:
  history=choose_folder(project,folder)/'History'
  if history.is_dir():paths+=list(history.glob('*TPORT_MTM_COMMERCIAL*.xlsb'))
 paths=sorted(set(p for p in paths if p.is_file() and not p.name.startswith('~$')))
 if not paths:raise ValueError('No matching daily XLSB files found. Expected date-prefixed or plain TPORT_MTM_COMMERCIAL names. No nightly fallback.')
 log={'startedUtc':utc(),'files':[],'status':'SUCCESS'}
 with archive.exclusive():
  for path in paths:
   print('\nImporting '+path.name,flush=True)
   try:result=import_file(archive,path,reader);log['files'].append(result);print(result['status']+'; snapshots '+', '.join(x['date'] for x in result['snapshots']),flush=True)
   except Exception as e:
    log['files'].append({'file':str(path),'status':'FAILED','error':str(e)});log['status']='PARTIAL_FAILURE';print('FAILED: '+str(e),flush=True)
  log['finishedUtc']=utc();atomic_json(archive.path/'last_import.json',log)
  logs=archive.path/'logs';logs.mkdir(exist_ok=True);atomic_json(logs/('import_'+uuid.uuid4().hex+'.json'),log)
  write_catalog_view(archive,archive.load())
 if log['status']!='SUCCESS':raise ValueError('One or more files failed. Successful files are archived; see snapshot_archive/last_import.json. No dashboard was overwritten.')
 return log

def write_catalog_view(archive,catalog):
 rows=[]
 for d,versions in sorted(catalog['snapshots'].items()):
  for v,m in versions.items():rows.append({'date':d,'version':v,'rows':m['rows'],'MTM':m['MTM'],'Fee':m['Fee'],'Total':m['Total'],'sourceFlags':m['sourceFlags'],'files':[catalog['sources'][s]['fileName'] for s in m['sources']],'financialFingerprint':m['financialFingerprint']})
 atomic_json(archive.path/'available_dates.json',{'updatedUtc':utc(),'snapshots':rows})

def resolve_version(catalog,d,version=None):
 iso(d)
 versions=catalog['snapshots'].get(d)
 if not versions:raise ValueError('Snapshot date unavailable: '+d)
 if version:
  matches=[k for k in versions if k.startswith(version)]
  if len(matches)!=1:raise ValueError('Version prefix is missing or ambiguous for '+d)
  return versions[matches[0]]
 if len(versions)!=1:raise ValueError('Multiple versions for '+d+'. Choose an explicit version; none is automatically preferred.')
 return next(iter(versions.values()))

def verify_payload(archive,m):
 p=archive.resolve(m['payload'])
 if not p.is_file() or sha(p)!=m['payloadSha256']:raise ValueError('Snapshot payload missing or corrupt: '+str(p))
 return p

def pair_payload(archive,catalog,current,baseline):
 dicts={k:[] for k in COLUMNS[:-2]};lookups={k:{} for k in dicts};records=[];controls={};blank=Counter();refs=[]
 for m in (baseline,current):
  p=verify_payload(archive,m);n=0;mtm=fee=0.
  with gzip.open(p,'rt',encoding='utf-8') as f:
   for line in f:
    item=json.loads(line);values=item['values']
    if len(values)!=len(COLUMNS) or values[0]!=m['date']:raise ValueError('Snapshot record schema/date mismatch')
    row=[]
    for k,v in zip(COLUMNS[:-2],values[:-2]):
     if v not in lookups[k]:lookups[k][v]=len(dicts[k]);dicts[k].append(v)
     row.append(lookups[k][v])
     if v=='(Blank)':blank[k]+=1
    nums=values[-2:]
    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in nums):raise ValueError('Invalid archived measure')
    row+=nums;records.append(row);n+=1;mtm+=nums[0];fee+=nums[1]
  if n!=m['rows'] or abs(mtm-m['MTM'])>.001 or abs(fee-m['Fee'])>.001:raise ValueError('Archived control totals do not reconcile')
  controls[m['date']]={'rows':n,'MTM':mtm,'Fee':fee,'Total':mtm+fee}
  refs.append({'date':m['date'],'version':m['version'],'sourceFiles':[catalog['sources'][s]['fileName'] for s in m['sources']],'sourceSha256':m['sources'],'sourceFlags':m['sourceFlags'],'financialFingerprint':m['financialFingerprint'],'payloadOriginSourceSha256':m['payloadOriginSourceSha256']})
 warnings=list(dict.fromkeys(current['warnings']+baseline['warnings']))+[
  'Historical endpoint valuation comparison, not realized P&L or curve-shift attribution.',
  'New Deal / C-Shift and other source-relative flags retain each selected report version context; they are not interval classifications.',
  'Source Year2 buckets and all source delivery months are retained. Bucket labels may change across distant dates; no common-bucket restatement or FX conversion is applied.'
 ]
 c=controls[current['date']];b=controls[baseline['date']]
 comparison={'currentDate':current['date'],'priorDate':baseline['date'],'currentRowCount':c['rows'],'priorRowCount':b['rows'],'Current_Disc_MTM':c['MTM'],'Prior_Disc_MTM':b['MTM'],'Disc_MTM_Change':c['MTM']-b['MTM'],'Current_Disc_Fee':c['Fee'],'Prior_Disc_Fee':b['Fee'],'Disc_Fee_Change':c['Fee']-b['Fee'],'Current_AllIn':c['Total'],'Prior_AllIn':b['Total'],'AllIn_Change':c['Total']-b['Total']}
 meta={'version':VERSION,'engineVersion':VERSION,'sourceFile':'Archived snapshot pair','generatedUtc':utc(),'reader':'versioned snapshot archive','dates':sorted(controls),'current':current['date'],'prior':baseline['date'],'population':'Raw DPR_RiskAnalysis; selected archived endpoints; no preset exclusions applied','rowCount':len(records),'skippedUndatedRows':None,'blankCounts':dict(blank),'fieldMapping':current['mapping'],'warnings':warnings,'missingOptionalFields':sorted(set(current['missingOptionalFields']+baseline['missingOptionalFields'])),'controls':controls,'comparison':comparison,'selectedSnapshots':refs,'absenceConvention':'A genuinely absent position contributes zero on the absent side of two loaded endpoints. Missing snapshots are rejected. Presence is not new-deal classification.'}
 return {'meta':meta,'columns':COLUMNS,'dicts':dicts,'rows':records}

NOTICE_JS=r'''(()=>{function start(){const D=window.PNL_DATA;if(!D?.meta?.selectedSnapshots)return;const panel=document.createElement('section');panel.id='snapshotPairContext';panel.style.cssText='flex-shrink:0;padding:6px 14px;background:var(--navy-050,#EEF4FB);border-bottom:1px solid var(--line,#DDE3EA);font:11px Segoe UI,Arial,sans-serif;color:var(--ink-700,#334155);display:flex;gap:10px;align-items:center;flex-wrap:wrap';const label=document.createElement('span');label.textContent='ARCHIVED PAIR · '+D.meta.current+' vs '+D.meta.prior+' · source flags are report-relative, not interval attribution';const button=document.createElement('button');button.type='button';button.textContent='Snapshot sources';button.style.cssText='font:inherit;padding:3px 8px;border:1px solid var(--line-strong,#C3CCD7);border-radius:4px;background:var(--surface,#fff);color:inherit;cursor:pointer';const dialog=document.createElement('dialog');dialog.style.cssText='max-width:680px;width:90vw;border:1px solid #C3CCD7;border-radius:6px;padding:18px';const title=document.createElement('h2');title.textContent='Selected snapshot provenance';const pre=document.createElement('pre');pre.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;font:12px Segoe UI,Arial,sans-serif';pre.textContent=D.meta.selectedSnapshots.map(s=>s.date+'\nVersion: '+s.version+'\nSource: '+s.sourceFiles.join(', ')+'\nStored daily flags: '+JSON.stringify(s.sourceFlags)).join('\n\n')+'\n\n'+D.meta.warnings.join('\n');const close=document.createElement('button');close.textContent='Close';close.onclick=()=>dialog.close();dialog.append(title,pre,close);document.body.appendChild(dialog);button.onclick=()=>dialog.showModal();panel.append(label,button);const kpi=document.querySelector('.v04-kpis');if(kpi)kpi.after(panel);else document.querySelector('header')?.after(panel);}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>requestAnimationFrame(start));else requestAnimationFrame(start);})();'''

def copy_ui(project,out):
 ws=project/'workspace';pages=[p for p in ws.glob('*.html') if p.name in ('index.html','index_v0_4.html')]
 if not pages:raise ValueError('Existing dashboard page not found')
 for name in ('workspace.js','workspace.css','xlsx_export.js'):
  if not (ws/name).is_file():raise ValueError('Existing dashboard asset missing: '+name)
 # Only UI assets; never copy stale data or source audit files.
 allowed={'.js','.css','.png','.jpg','.jpeg','.svg','.webp','.woff','.woff2','.ico','.html'}
 for p in ws.rglob('*'):
  if not p.is_file() or p.suffix.lower() not in allowed or p.name=='data.js':continue
  if p.suffix.lower()=='.html' and p not in pages:continue
  dest=out/p.relative_to(ws);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
 for page in pages:
  dest=out/page.name;html=dest.read_text(encoding='utf-8-sig')
  if not re.search(r'</body\s*>',html,re.I):raise ValueError('Invalid existing dashboard HTML')
  html=re.sub(r'</body\s*>',lambda m:'\n<script id="snapshot-pair-context">'+NOTICE_JS+'</script>\n'+m.group(),html,count=1,flags=re.I);dest.write_text(html,encoding='utf-8')
 return 'index_v0_4.html' if (out/'index_v0_4.html').exists() else 'index.html'

def publish(project,current_date,baseline_date,current_version=None,baseline_version=None,open_page=False):
 if iso(current_date)!=current_date or iso(baseline_date)!=baseline_date or current_date<=baseline_date:raise ValueError('Current must be later than Baseline; use available YYYY-MM-DD dates')
 archive=Archive(project);started=time.perf_counter()
 with archive.exclusive():
  catalog=archive.load();c=resolve_version(catalog,current_date,current_version);b=resolve_version(catalog,baseline_date,baseline_version)
  if c['columns']!=COLUMNS or b['columns']!=COLUMNS:raise ValueError('Snapshot normalized schema mismatch')
  # Fail rather than mixing differently mapped source schemas.
  if c['schemaHash']!=b['schemaHash']:raise ValueError('Snapshot source schemas/mappings differ. Explicit migration review required; nothing published.')
  existing=project/'workspace'/'data.js'
  if existing.is_file():
   original=existing.read_text(encoding='utf-8-sig').strip()
   match=re.fullmatch(r'(?:window\.)?PNL_DATA\s*=\s*(\{.*\})\s*;?',original,re.S)
   if not match:raise ValueError('Existing data.js is not the supported PNL_DATA JSON format. No dashboard files changed.')
   installed=json.loads(match.group(1))
   if installed.get('columns')!=COLUMNS:raise ValueError('Installed dashboard column schema differs from this archive publisher. No dashboard files changed; mapping review required.')
   del installed,original
  payload=pair_payload(archive,catalog,c,b)
  views=project/'history_views';views.mkdir(exist_ok=True)
  run_id=current_date+'_vs_'+baseline_date+'_'+uuid.uuid4().hex[:10];stage=views/('.pending_'+run_id);final=views/run_id;stage.mkdir()
  try:
   page=copy_ui(project,stage)
   with (stage/'data.js').open('w',encoding='utf-8') as f:f.write('window.PNL_DATA=');json.dump(payload,f,ensure_ascii=True,separators=(',',':'),allow_nan=False);f.write(';\n')
   atomic_json(stage/'build_report.json',payload['meta'])
   with gzip.open(stage/'source_records.csv.gz','wt',encoding='utf-8',newline='') as audit:
    writer=csv.writer(audit);writer.writerow(['SnapshotDate','SnapshotVersion','PayloadOriginSourceSha256','SourceRow']+c['headers'])
    for m in (b,c):
     with gzip.open(verify_payload(archive,m),'rt',encoding='utf-8') as src:
      for line in src:
       record=json.loads(line);writer.writerow([m['date'],m['version'],m['payloadOriginSourceSha256'],record['sourceRow']]+[x.get('isoDate') if isinstance(x,dict) and 'isoDate' in x else x for x in record['raw']])
   timing={'publishedUtc':utc(),'current':current_date,'baseline':baseline_date,'selectedVersions':{'current':c['version'],'baseline':b['version']},'records':len(payload['rows']),'publishSeconds':time.perf_counter()-started,'status':'SUCCESS'}
   atomic_json(stage/'pair_publish_timing.json',timing)
   os.replace(stage,final)
   atomic_json(archive.path/'last_pair.json',{'page':str(final/page),'timing':timing,'comparison':payload['meta']['comparison']})
  except Exception:
   shutil.rmtree(stage,ignore_errors=True);raise
 print('Published '+current_date+' versus '+baseline_date+' to '+str(final/page))
 print('Original daily dashboard and source workbooks were not modified.')
 if open_page:webbrowser.open((final/page).as_uri())
 return final/page

def list_dates(project):
 a=Archive(project);c=a.load();write_catalog_view(a,c)
 for d,versions in sorted(c['snapshots'].items()):
  print(d+' | '+str(len(versions))+' version(s)')
  for v,m in versions.items():print('  '+v[:16]+' | '+str(m['rows'])+' rows | Total '+format(m['Total'],',.2f')+' | '+', '.join(c['sources'][s]['fileName'] for s in m['sources']))
 if not c['snapshots']:print('Archive is empty. Run IMPORT_SNAPSHOTS.cmd first.')

def gui_publish(project):
 import tkinter as tk
 from tkinter import ttk,messagebox
 archive=Archive(project);catalog=archive.load();dates=sorted(catalog['snapshots'])
 if len(dates)<2:raise ValueError('At least two archived dates required. Run IMPORT_SNAPSHOTS.cmd first.')
 app=tk.Tk();app.title('Commercial MTM | Select archived date pair');app.geometry('900x480');app.configure(bg='#EEF4FB')
 frame=ttk.Frame(app,padding=20);frame.pack(fill='both',expand=True)
 ttk.Label(frame,text='Publish an archived valuation comparison',font=('Segoe UI',16,'bold')).pack(anchor='w')
 ttk.Label(frame,text='Current must be later than Baseline. Multiple versions require explicit selection.').pack(anchor='w',pady=(6,18))
 vars={};boxes={};version_ids={};date_boxes={}
 for role,default in [('Current',dates[-1]),('Baseline',dates[-2])]:
  row=ttk.Frame(frame);row.pack(fill='x',pady=8);ttk.Label(row,text=role,width=12).pack(side='left')
  dv=tk.StringVar(value=default);vv=tk.StringVar();vars[role]=(dv,vv)
  date_box=ttk.Combobox(row,textvariable=dv,values=dates,state='readonly',width=14);date_box.pack(side='left',padx=(0,12));date_boxes[role]=date_box
  version_box=ttk.Combobox(row,textvariable=vv,state='readonly',width=76);version_box.pack(side='left',fill='x',expand=True);boxes[role]=version_box
 def update(role):
  dv,vv=vars[role];versions=catalog['snapshots'][dv.get()];labels=[];ids=[]
  for v,m in versions.items():
   files=', '.join(catalog['sources'][s]['fileName'] for s in m['sources']);labels.append(v[:12]+' | '+str(m['rows'])+' rows | '+files);ids.append(v)
  boxes[role]['values']=labels;version_ids[role]=ids
  if len(labels)==1:boxes[role].current(0)
  else:vv.set('')
 for role in vars:update(role)
 for role,widget in date_boxes.items():widget.bind('<<ComboboxSelected>>',lambda e,r=role:update(r))
 note=ttk.Label(frame,text='Source New Deal / C-Shift flags remain report-relative. This is valuation change, not P&L attribution.\nAll source delivery months and existing Year2 labels are retained. No FX conversion or preset rules are added.',wraplength=820);note.pack(anchor='w',pady=20)
 result={}
 def accept():
  try:
   c=vars['Current'][0].get();b=vars['Baseline'][0].get()
   if c<=b:raise ValueError('Current must be later than Baseline.')
   selections={}
   for role in vars:
    i=boxes[role].current()
    if i<0:raise ValueError('Choose an explicit '+role+' snapshot version.')
    selections[role]=version_ids[role][i]
   result.update(current=c,baseline=b,current_version=selections['Current'],baseline_version=selections['Baseline']);app.destroy()
  except Exception as e:messagebox.showerror('Select a valid pair',str(e),parent=app)
 ttk.Button(frame,text='Publish selected pair',command=accept).pack(anchor='e');app.mainloop()
 if not result:raise ValueError('Pair selection cancelled; nothing published')
 return publish(project,result['current'],result['baseline'],result['current_version'],result['baseline_version'],True)

def open_last(project):
 p=Archive(project).path/'last_pair.json'
 if not p.exists():raise ValueError('No historical pair published yet')
 page=Path(json.loads(p.read_text())['page'])
 if not page.is_file():raise ValueError('Last published page is missing; publish the pair again')
 webbrowser.open(page.as_uri())

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['import','list','publish','choose','open-last']);ap.add_argument('--project');ap.add_argument('--folder');ap.add_argument('--files',nargs='+');ap.add_argument('--reader',choices=['pyxlsb','calamine'],default='pyxlsb');ap.add_argument('--include-history',action='store_true');ap.add_argument('--current');ap.add_argument('--baseline');ap.add_argument('--current-version');ap.add_argument('--baseline-version');ap.add_argument('--open',action='store_true');a=ap.parse_args()
 try:
  project=project_at(a.project)
  if a.action=='import':run_import(project,a.folder,a.files,a.reader,a.include_history)
  elif a.action=='list':list_dates(project)
  elif a.action=='choose':gui_publish(project)
  elif a.action=='open-last':open_last(project)
  else:
   if not a.current or not a.baseline:raise ValueError('--current and --baseline are required')
   publish(project,a.current,a.baseline,a.current_version,a.baseline_version,a.open)
 except Exception as e:print('STOPPED: '+str(e),file=sys.stderr);return 1
 return 0
if __name__=='__main__':sys.exit(main())
