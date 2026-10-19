#!/usr/bin/env python3
"""Generate a fixed-pair HTML report beside this script. Never uploads or edits the app."""
import argparse,ast,base64,gzip,hashlib,html,importlib.util,json,math,re,shutil,subprocess,sys,tempfile
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
LIMIT=10_000_000

def once(s,a,b,label):
    if s.count(a)!=1:raise ValueError('Unsupported '+label+': expected one anchor. Sources unchanged.')
    return s.replace(a,b,1)

def safe_json(x):
    return json.dumps(x,ensure_ascii=True,separators=(',',':'),allow_nan=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')

CORE=r"""
function publisherNewDealCount(){
 for(const k of ['Date','DealID','NewDealCurveShift'])if(!Number.isInteger(I[k])||!Array.isArray(dict[k]))throw Error('Missing column/dictionary: '+k);
 const ids=new Set();for(const r of D.rows){
  if(value(r,'Date')!==S.current||!match(r))continue;
  if(String(value(r,'NewDealCurveShift')??'').trim().toLowerCase()!=='new deal')continue;
  const id=String(value(r,'DealID')??'').trim();if(id)ids.add(id);
 }return ids.size;
}
const publisherOriginalAggregate=aggregate;
aggregate=function(){const result=publisherOriginalAggregate();window.dispatchEvent(new CustomEvent('publisher:aggregated'));return result;};
"""
VIEWER=r"""
(()=>{'use strict';const $=id=>document.getElementById(id);
 function render(){
  const c=document.querySelector('.v04-kpi[data-metric="Movements"],.v04-kpi[data-metric="NewDeals"]');if(!c)return false;
  c.dataset.metric='NewDeals';c.dataset.sign='zero';c.classList.remove('is-active');
  const l=c.querySelector('.k-label'),v=c.querySelector('.k-value'),s=c.querySelector('.k-sub');
  if(!l||!v||!s)throw Error('New Deals card structure changed.');
  l.textContent='New Deals';s.textContent='Distinct deals flagged New Deal · Current';
  try{v.textContent=PNL_APP.publisherNewDealCount().toLocaleString('en-US');c.dataset.publisherState='ready';}
  catch(e){v.textContent='Unavailable';c.dataset.publisherState='error';c.title=e.message;console.error(e);}return true;
 }
 function start(){
  if(!window.PNL_APP?.publisherNewDealCount)throw Error('Published core unavailable.');
  for(const id of ['current','prior']){const e=$(id);if(e){e.disabled=true;e.title='Fixed published date pair';}}
  for(const e of document.querySelectorAll('select'))if(e.disabled&&[...e.options].some(o=>o.textContent.trim()==='Raw population — no preset')){
   let c=e.closest('label,.field,.control,.filter-control');
   if(!c){let p=e.parentElement;for(let i=0;p&&i<3;i++,p=p.parentElement)if(p.querySelectorAll('select').length===1&&p.textContent.trim().startsWith('Deals')){c=p;break;}}
   if(c&&/Deals/i.test(c.textContent))c.dataset.publisherHidden='true';
  }
  if(!render())throw Error('New Deals card missing.');
  if(document.querySelector('.v04-kpi[data-metric="NewDeals"]')?.dataset.publisherState!=='ready')throw Error('New Deals unavailable.');
  if(!window.PNL_DEFAULT_FILTERS?.applied||PNL_DEFAULT_FILTERS.warnings.length)throw Error('Default reporting scope could not be verified.');
  $('publisher-banner').dataset.state='loaded';$('publisher-load').textContent='Published snapshot loaded. Validate scope before use.';
 }
 window.addEventListener('publisher:aggregated',render);
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>requestAnimationFrame(start));else requestAnimationFrame(start);
})();
"""
BOOT=r"""
(async()=>{'use strict';const status=document.getElementById('publisher-load');
 function fail(e){status.textContent='REPORT NOT READY: '+(e.message||e);document.getElementById('publisher-banner').dataset.state='error';console.error(e);}
 window.addEventListener('error',e=>fail(e.error||e));
 try{
  if(!globalThis.DecompressionStream)throw Error('Embedded gzip decoder unavailable in this browser.');
  const bytes=Uint8Array.from(atob(document.getElementById('publisher-payload').textContent.trim()),c=>c.charCodeAt(0));
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  window.PNL_DATA=JSON.parse(await new Response(stream).text());
  const mem=new Map();window.PNL_PUBLISHER_STORAGE={getItem:k=>mem.get(k)??null,setItem:(k,v)=>mem.set(k,String(v)),removeItem:k=>mem.delete(k),clear:()=>mem.clear()};
  const scripts=JSON.parse(document.getElementById('publisher-scripts').textContent);
  for(const code of scripts){const el=document.createElement('script');el.textContent=code;document.body.appendChild(el);}
 }catch(e){fail(e);}
})();
"""
STYLE="""
#publisher-banner{padding:8px 18px;background:var(--surface,#eef4fb);color:var(--text,#19324c);font:12px Segoe UI,Arial,sans-serif;border-bottom:1px solid var(--line,#ccd7e3);flex-shrink:0}
#publisher-banner[data-state="error"]{background:#fff0f0;color:#8c1010}
#publisher-banner pre{white-space:pre-wrap;max-height:180px;overflow:auto}
[data-publisher-hidden="true"]{display:none!important}
.v04-kpi[data-metric="NewDeals"]{border-top-color:var(--blue,#2563eb)!important;outline:none!important;box-shadow:none!important;background:var(--surface,#fff)!important}
.v04-kpi[data-metric="NewDeals"] .k-value{color:var(--text,#19324c)!important}
@media print{#publisher-banner details{display:none}}
"""

def patch_adapter(source):
    blocks=list(re.finditer(r'<script\b[^>]*>(.*?)</script\s*>',source,re.I|re.S))
    found=[b for b in blocks if 'function countMovements()' in b.group(1)]
    if len(found)!=1:raise ValueError('Expected one original inline visual adapter.')
    b=found[0];s=b.group(1)
    s=once(s,"if(m!=='Movements'){","if(['MTM','Fee','Total'].includes(m)){",'financial gate')
    s=once(s,'function countMovements(){','function countMovements(){return; /* retired in published report */','movement renderer')
    s=once(s,'lastKpiRoot=A.root;countMovements();',"lastKpiRoot=A.root;if(document.querySelector('.v04-kpi[data-metric=\"Movements\"]'))countMovements();",'movement call')
    return source[:b.start(1)]+s+source[b.end(1):]

def validate_payload(p):
    cols=p['columns'];ds=p['dicts'];ix={k:i for i,k in enumerate(cols)}
    for k in ['Date','DealID','NewDealCurveShift','MTM','Fee']:
        if k not in ix:raise ValueError('Required column missing: '+k)
    for k in ['Date','DealID','NewDealCurveShift']:
        if not isinstance(ds.get(k),list):raise ValueError('Required dictionary missing: '+k)
    dates=[p['meta']['current'],p['meta']['prior']]
    totals={d:{'rows':0,'MTM':Decimal(0),'Fee':Decimal(0)} for d in dates}
    for row in p['rows']:
        if len(row)!=len(cols):raise ValueError('Invalid record width.')
        for k,labels in ds.items():
            if k not in ix or not isinstance(labels,list):raise ValueError('Invalid dictionary: '+k)
            n=row[ix[k]]
            if isinstance(n,bool) or not isinstance(n,int) or not 0<=n<len(labels):raise ValueError('Invalid dictionary index: '+k)
        day=ds['Date'][row[ix['Date']]]
        if day not in totals:raise ValueError('Unexpected valuation date.')
        totals[day]['rows']+=1
        for k in ['MTM','Fee']:
            n=row[ix[k]]
            if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n):raise ValueError('Invalid financial measure.')
            totals[day][k]+=Decimal(str(n))
    for d in totals:
        totals[d]['Total']=str(totals[d]['MTM']+totals[d]['Fee'])
        for k in ['MTM','Fee']:totals[d][k]=str(totals[d][k])
    return totals

def build_report(app,payload):
    controls=validate_payload(payload);ws=app.WORKSPACE
    page='index_v0_4.html' if (ws/'index_v0_4.html').is_file() else 'index.html'
    source=(ws/page).read_text(encoding='utf-8-sig')
    if 'local-date-controls' in source:raise ValueError('Use original workspace HTML, not a served copy.')
    defaults=re.search(r'const RULES=(\{.*?\});',source,re.S)
    if not defaults:raise ValueError('Original five-default-filter rules missing.')
    rules=ast.literal_eval(re.sub(r'([,{])([A-Za-z][A-Za-z0-9_]*):',r"\1'\2':",defaults.group(1)))
    if len(rules)!=5:raise ValueError('Expected five default filter rules.')
    for key in rules:
        if not isinstance(payload['dicts'].get(key),list):raise ValueError('Default filter dictionary missing: '+key)
    source=patch_adapter(source)
    core=app.build_served_core().decode('utf-8')
    core=once(core,'window.PNL_APP={',CORE+'\nwindow.PNL_APP={publisherNewDealCount,','core export')
    core=once(core,'window.PNL_APP={publisherNewDealCount,replaceData,','window.PNL_APP={publisherNewDealCount,','pair replacement export')
    scripts=[];hashes={'workspace HTML':hashlib.sha256((ws/page).read_bytes()).hexdigest(),'served core':hashlib.sha256(core.encode()).hexdigest()}
    def read_asset(name):
        p=ws/name
        if p.parent.resolve()!=ws.resolve():raise ValueError('Asset outside workspace.')
        raw=p.read_bytes();hashes[name]=hashlib.sha256(raw).hexdigest();return raw.decode('utf-8-sig')
    def script_replace(m):
        src=re.search(r'\bsrc\s*=\s*[\'"]([^\'"]+)[\'"]',m.group(1),re.I)
        if src:
            name=src.group(1)
            if name=='data.js':return ''
            if name=='workspace.js':code=core
            elif name=='xlsx_export.js':code=read_asset(name)
            else:raise ValueError('Unrecognized script: '+name)
        else:code=m.group(2)
        code=re.sub(r'\b(?:localStorage|sessionStorage)\b','PNL_PUBLISHER_STORAGE',code)
        if re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(',code):raise ValueError('Network-dependent script cannot be published.')
        scripts.append(code);return ''
    source=re.sub(r'<script\b([^>]*)>(.*?)</script\s*>',script_replace,source,flags=re.I|re.S)
    if not any('publisherNewDealCount' in s for s in scripts):raise ValueError('Core script missing.')
    def style_replace(m):
        href=re.search(r'href=[\'"]([^\'"]+)[\'"]',m.group(),re.I)
        if not href or href.group(1)!='workspace.css':raise ValueError('Unexpected stylesheet.')
        css=read_asset('workspace.css')
        if '@import' in css:raise ValueError('External CSS import unsupported.')
        for u in re.findall(r'url\((.*?)\)',css,re.I):
            if not u.strip(' \t\'"').startswith(('data:','#')):raise ValueError('External CSS resource unsupported.')
        return '<style>'+css+'</style>'
    source=re.sub(r'<link\b[^>]*rel=[\'"]stylesheet[\'"][^>]*>',style_replace,source,flags=re.I)
    if re.search(r'<(?:img|iframe|script)\b[^>]*\bsrc=[\'"](?!data:)',source,re.I):raise ValueError('External resources remain.')
    current=payload['meta']['current'];prior=payload['meta']['prior'];published=datetime.now(timezone.utc).isoformat()
    ix={k:i for i,k in enumerate(payload['columns'])}
    allowed={k:{i for i,v in enumerate(payload['dicts'][k]) if ('' if str(v).strip()=='(Blank)' or v is None else str(v).strip()) in values} for k,values in rules.items()}
    if any(not a for a in allowed.values()):raise ValueError('A default filter has no matching labels. Verify source mapping before publication.')
    filtered_rows=[r for r in payload['rows'] if all(r[ix[k]] in a for k,a in allowed.items())]
    filtered_payload={**payload,'rows':filtered_rows}
    default_controls=validate_payload(filtered_payload)
    new_ids={str(payload['dicts']['DealID'][r[ix['DealID']]] if payload['dicts']['DealID'][r[ix['DealID']]] is not None else '').strip() for r in filtered_rows
      if payload['dicts']['Date'][r[ix['Date']]]==current
      and str(payload['dicts']['NewDealCurveShift'][r[ix['NewDealCurveShift']]]).strip().lower()=='new deal'}
    new_ids.discard('')
    info={'publisherVersion' :'1.0-pilot','publishedUtc':published,'current':current,'prior':prior,
      'selectedSnapshots':payload['meta'].get('selectedSnapshots',[]),'rawUnfilteredControls':controls,'defaultFilterRules':rules,'defaultFilteredControls':default_controls,'defaultNewDeals':len(new_ids),
      'classificationLabels':payload['dicts']['NewDealCurveShift'],
      'scope':'Original five default filters on load; viewer session filters interactive. Not publisher local-session filters.',
      'warning':'All embedded rows are available to recipients. Filters are not security boundaries.'}
    banner='<section id="publisher-banner" data-state="loading"><strong>Published snapshot: '+html.escape(current)+' vs '+html.escape(prior)+'</strong> | Published '+html.escape(published)+'<div id="publisher-load" role="status">Loading embedded report. Not yet ready.</div><details><summary>Data info / publication details</summary><pre>'+html.escape(json.dumps(info,indent=2))+'</pre></details></section>'
    source=re.sub(r'(<body\b[^>]*>)',lambda m:m.group()+banner,source,count=1,flags=re.I)
    source=once(source,'</head>','<style>'+STYLE+'</style></head>','HTML head')
    source=source.replace('Data is published locally, with no external scripts or data transmission. Rebuild the workspace to pick up a newly refreshed workbook. Files contain company data; keep them in authorized locations.','This is a fixed published date pair, not live data. Filters affect only this viewing session. Publish again for new dates. Embedded rows contain company data; keep the report in authorized locations.')
    scripts.append(VIEWER)
    packed=base64.b64encode(gzip.compress(json.dumps(payload,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode(),mtime=0)).decode('ascii')
    add='<script type="application/octet-stream" id="publisher-payload">'+packed+'</script><script type="application/json" id="publisher-scripts">'+safe_json(scripts)+'</script><script>'+BOOT+'</script>'
    source=once(source,'</body>',add+'</body>','HTML body')
    content=source.encode('utf-8')
    info.update(htmlBytes=len(content),htmlSha256=hashlib.sha256(content).hexdigest(),assetHashes=hashes,javascriptParser='not available locally')
    node=shutil.which('node')
    if node:
        with tempfile.TemporaryDirectory() as d:
            for i,code in enumerate(scripts+[BOOT]):
                f=Path(d)/(str(i)+'.js');f.write_text(code,encoding='utf-8')
                r=subprocess.run([node,'--check',str(f)],capture_output=True,text=True)
                if r.returncode:raise ValueError('JavaScript syntax check failed: '+r.stderr)
        info['javascriptParser']='node --check passed'
    return content,info

def load_app():
    spec=importlib.util.spec_from_file_location('publisher_local_app',ROOT/'local_date_app.py')
    if spec is None or spec.loader is None:raise ValueError('Cannot load local app.')
    app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
    for name in ['load_manager','load_selections','prepare_pair','build_served_core']:
        if not callable(getattr(app,name,None)):raise ValueError('App interface missing: '+name)
    app.MANAGER=app.load_manager();return app

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--current');p.add_argument('--prior');p.add_argument('--yes',action='store_true');args=p.parse_args()
    app=load_app();saved=app.load_selections();dates=sorted(saved)
    if len(dates)<2:raise ValueError('At least two reviewed dates required. Review in the local app first.')
    print('Reviewed dates: '+', '.join(dates))
    current=args.current or input('Current date ['+dates[-1]+']: ').strip() or dates[-1]
    prior=args.prior or input('Prior date ['+dates[-2]+']: ').strip() or dates[-2]
    if current not in saved or prior not in saved:raise ValueError('Both dates must have saved reviewed selections.')
    print('Publish '+current+' vs '+prior+' using saved versions. Includes ALL rows for both dates.')
    if not args.yes and input('Type PUBLISH to generate: ').strip()!='PUBLISH':print('Cancelled.');return 0
    query={'current':[current],'prior':[prior],'currentVersion':[saved[current]['version']],'priorVersion':[saved[prior]['version']]}
    payload=app.prepare_pair(query)
    if payload['meta']['current']!=current or payload['meta']['prior']!=prior:raise ValueError('Pair date mismatch.')
    content,info=build_report(app,payload)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');prefix='Commercial_MTM_'+current+'_vs_'+prior+'_'+stamp
    report=ROOT/(prefix+'.html');manifest=ROOT/(prefix+'_manifest.json')
    if len(content)>LIMIT:
        info['status']='BLOCKED_SIZE_LIMIT';manifest.write_text(json.dumps(info,indent=2),encoding='utf-8')
        raise ValueError('Report is '+str(len(content))+' bytes; exceeds '+str(LIMIT)+'. No HTML emitted. See '+manifest.name)
    info['status']='GENERATED_NOT_RECONCILED'
    with report.open('xb') as f:f.write(content)
    manifest.write_text(json.dumps(info,indent=2),encoding='utf-8')
    print('GENERATED: '+report.name+' ('+str(len(content))+' bytes)')
    print('MANIFEST: '+manifest.name)
    print('Reconcile locally, then upload ONLY the HTML beside your successful SharePoint test.')
    print('Sandbox, export/print, performance and independent count still require pilot checks.')
    return 0
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:print('STOPPED:',e,file=sys.stderr);sys.exit(1)
