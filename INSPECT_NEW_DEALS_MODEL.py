#!/usr/bin/env python3
"""Read-only diagnostic for New Deals KPI field mapping."""
from pathlib import Path
import json,re
root=Path(__file__).resolve().parent
ws=root/'workspace'
out=root/'NEW_DEALS_MODEL_REPORT.txt'
parts=[]
for name in ('workspace.js','data.js'):
 p=ws/name
 if not p.is_file():
  parts.append(f'{name}: MISSING')
  continue
 text=p.read_text(encoding='utf-8-sig',errors='replace')
 parts.append(f'[{name}]')
 for pattern in ('Deal','DEAL','New Deal','NewDeal','C-Shift','Curve Shift','Raw population','Movements'):
  hits=[]
  for m in re.finditer(re.escape(pattern),text,re.I):
   a=max(0,m.start()-100);b=min(len(text),m.end()+140)
   hit=' '.join(text[a:b].split())
   if hit not in hits:hits.append(hit)
  parts.append(f'\n{pattern}: {len(hits)} unique context hit(s)')
  parts.extend('  '+h for h in hits[:20])
 out.write_text('\n'.join(parts),encoding='utf-8')
print(f'Created read-only diagnostic: {out.name}')
print('No workspace, archive, selection, or source file was modified.')
