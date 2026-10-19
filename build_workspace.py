"""Forward P&L Workspace 0.3: read-only source extraction and offline publication.
No source macros, refreshes, exclusions, or deduplication. No external web assets.
"""
import argparse,csv,gzip,json,math,os,shutil,sys,hashlib
from collections import Counter,defaultdict
from datetime import datetime,date,timedelta,timezone
from pathlib import Path

FIELDS=[('ActivityBucket','Activity Bucket'),('Region','Region'),('AMA','AMA or Non-AMA'),('Strategy','Revised Strategy'),('DealType','DEALTYPE'),('Curve','Abbrev_Val_Pool'),('Counterparty','EXTBUNIT'),('DealID','DEALID'),('Year2',('Year2','Year Group')),('Year','Year'),('ContractMonth','ContractMonth'),('GeoRegion','GeoRegion'),('TradeMonth','Trade Month'),('SeasonDetail','Season Detail'),('NewDealCurveShift','New Deal / C-Shift'),('ServiceType','SERVICETYPE'),('EncumberedTag','Encumbered Tag'),('FwdMonthIncl','Fwd_Month_Incl'),('ValidEconDealType','Valid Econ Deal Type'),('ReportingType','Reporting Type'),('InterruptCommTrans','Interrupt Comm-Trans?')]
REQUIRED=[x[0] for x in FIELDS[:11]]

def iso(v,month=False):
    if v is None or v=='': return ''
    if isinstance(v,datetime): d=v.date()
    elif isinstance(v,date): d=v
    elif isinstance(v,(int,float)):
        if not math.isfinite(v): raise ValueError('Invalid date number')
        d=(datetime(1899,12,30)+timedelta(days=v)).date()
    else:
        t=str(v).strip();d=None
        for fmt in ('%Y-%m-%d','%m/%d/%Y','%m-%d-%Y','%b-%Y','%Y%m'):
            try:d=datetime.strptime(t,fmt).date();break
            except ValueError:pass
        if d is None: raise ValueError('Unrecognized date: '+t)
    if not 1900<=d.year<=2200:raise ValueError('Date outside supported range: '+str(d))
    return d.replace(day=1).isoformat() if month else d.isoformat()

def text(v):
    if v is None or v=='':return '(Blank)'
    if isinstance(v,(date,datetime)):return iso(v)
    if isinstance(v,float) and v.is_integer():return str(int(v))
    return str(v).strip()

def money(v):
    if v is None or v=='':return 0.0
    n=float(v)
    if not math.isfinite(n):raise ValueError('Non-finite financial value')
    return n

def iter_source(path,reader):
    if reader=='calamine':
        from python_calamine import CalamineWorkbook
        w=CalamineWorkbook.from_path(str(path));s=w.get_sheet_by_name('DPR_RiskAnalysis')
        yield from s.iter_rows()
    else:
        from pyxlsb import open_workbook
        with open_workbook(str(path)) as w,w.get_sheet('DPR_RiskAnalysis') as s:
            for row in s.rows():yield [c.v for c in row]

def build(source,out,reader):
    source=source.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).isoformat();it=iter(iter_source(source,reader));headers=[str(x).strip() if x is not None else '' for x in next(it)]
    indices={};resolved={};warnings=[]
    for dest,names in FIELDS:
        candidates=names if isinstance(names,tuple) else (names,)
        for name in candidates:
            matches=[i for i,h in enumerate(headers) if h==name]
            if matches:
                indices[dest]=matches[-1];resolved[dest]={'source':name,'column':matches[-1]+1}
                if len(matches)>1:warnings.append(f'{name}: duplicate headers; selected column {matches[-1]+1}, consistent with v0.2.1')
                break
        if dest in REQUIRED and dest not in indices:raise ValueError('Missing required source field: '+str(names))
    for dest,name in [('Date','EODDATE'),('MTM','Economic Disc MTM'),('Fee','Disc Fee')]:
        if name not in headers:raise ValueError('Missing source field: '+name)
        indices[dest]=headers.index(name);resolved[dest]={'source':name,'column':indices[dest]+1}
    if resolved['Year2']['source']!='Year2':warnings.append('Year2 uses Year Group, as in v0.2.1; equivalence to pivot Year2 remains unconfirmed.')
    keys=['Date']+[x[0] for x in FIELDS];dicts={k:[] for k in keys};lookups={k:{} for k in keys};records=[];controls=defaultdict(lambda:[0,0.,0.]);blanks=Counter();skipped=0
    def code(k,v):
        if v not in lookups[k]:lookups[k][v]=len(dicts[k]);dicts[k].append(v)
        return lookups[k][v]
    def val(row,k):
        pos=indices.get(k);return row[pos] if pos is not None and pos<len(row) else None
    # Preserve every dated source row and all original source columns in a separate audit file.
    audit=out/'source_records.csv.gz'
    with gzip.open(audit,'wt',encoding='utf-8',newline='') as f:
        wr=csv.writer(f);wr.writerow(['SourceRow']+headers)
        for rowno,row in enumerate(it,2):
            dv=val(row,'Date')
            if dv is None or dv=='':skipped+=1;continue
            try:
                d=iso(dv);m=money(val(row,'MTM'));fee=money(val(row,'Fee'))
                values={'Date':d}
                for k,_ in FIELDS:
                    v=val(row,k)
                    if k=='ContractMonth':v=iso(v,True) if v not in (None,'') else '(Blank)'
                    elif k=='TradeMonth' and (isinstance(v,(date,datetime)) or isinstance(v,(int,float)) and 20000<v<100000):v=iso(v,True)
                    else:v=text(v)
                    values[k]=v
                    if v=='(Blank)':blanks[k]+=1
                records.append([code(k,values[k]) for k in keys]+[m,fee])
                c=controls[d];c[0]+=1;c[1]+=m;c[2]+=fee
                wr.writerow([rowno]+row)
            except Exception as exc:raise ValueError(f'Source row {rowno}: {exc}') from exc
            if len(records)%25000==0:print(f'Read {len(records):,} dated records',flush=True)
    dates=sorted(controls)
    if len(dates)<2:raise ValueError('At least two EODDATE snapshots required')
    meta={'version':'0.3.0','sourceFile':source.name,'generatedUtc':stamp,'reader':reader,'dates':dates,'current':dates[-1],'prior':dates[-2],'population':'Raw DPR_RiskAnalysis; no report exclusions or preset views applied','rowCount':len(records),'skippedUndatedRows':skipped,'blankCounts':dict(blanks),'fieldMapping':resolved,'warnings':warnings,'missingOptionalFields':[k for k,_ in FIELDS if k not in indices],'controls':{d:{'rows':v[0],'MTM':v[1],'Fee':v[2],'Total':v[1]+v[2]} for d,v in controls.items()},'absenceConvention':'A position genuinely absent from one loaded snapshot contributes zero on that side. Missing snapshots are rejected. Current-only/Prior-only is based on row presence, not nonzero values.'}
    payload={'meta':meta,'columns':keys+['MTM','Fee'],'dicts':dicts,'rows':records}
    # Encode as JSON, never as executable source strings from the workbook.
    js='window.PNL_DATA='+json.dumps(payload,ensure_ascii=True,separators=(',',':'),allow_nan=False)+';\n'
    tmp=out/'data.js.tmp';tmp.write_text(js,encoding='utf-8');os.replace(tmp,out/'data.js')
    (out/'build_report.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    here=Path(__file__).resolve().parent
    for name in ('index.html','workspace.css','workspace.js','xlsx_export.js'):
        shutil.copy2(here/name,out/name)
    print(f'COMPLETE: {len(records):,} dated rows; {dates[-1]} vs {dates[-2]}')
    print('Open '+str(out/'index.html'))
    return meta

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--file',default=r'O:\SEM\Common\Endur\AutoFiles\RISK\TPORT_MTM_COMMERCIAL_MM-DD-YY_.xlsb');ap.add_argument('--out',default='workspace');ap.add_argument('--reader',choices=['pyxlsb','calamine'],default='pyxlsb');a=ap.parse_args()
    try:build(Path(a.file),Path(a.out),a.reader)
    except Exception as e:print('BUILD FAILED: '+str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
