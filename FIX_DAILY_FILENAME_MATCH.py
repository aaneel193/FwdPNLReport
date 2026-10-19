"""Correct date-prefixed daily filename discovery; no data or workbook changes."""
from pathlib import Path
import json,shutil,sys
root=Path(__file__).resolve().parent
p=root/'daily_source_update.py'
try:
 if not p.is_file():raise ValueError('Place this file beside daily_source_update.py in the main project folder.')
 text=p.read_text(encoding='utf-8-sig');old='TPORT_MTM_COMMERCIAL*.xlsb';new='*TPORT_MTM_COMMERCIAL*.xlsb'
 if new in text:print('Date-prefixed matcher already installed. No changes required.')
 elif old not in text:raise ValueError('Expected filename pattern not found. Nothing changed.')
 else:
  backup=p.with_name(p.name+'.before_filename_fix')
  if not backup.exists():shutil.copy2(p,backup)
  updated=text.replace(old,new);compile(updated,str(p),'exec');p.write_text(updated,encoding='utf-8')
  print('Updated daily-file matcher to include date-prefixed names. Source selection remains explicit when multiple files match.')
 cfg=root/'daily_source_config.json'
 if cfg.exists():
  c=json.loads(cfg.read_text());c['pattern']=new;cfg.write_text(json.dumps(c,indent=2))
 print('No workbook, dashboard dataset, hierarchy, slicer, or financial calculation was changed.')
except Exception as e:print('NOT APPLIED: '+str(e));sys.exit(1)
