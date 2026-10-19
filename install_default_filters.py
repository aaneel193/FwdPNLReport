"""Install load-time default slicers; never modify data or core JS."""
from pathlib import Path
import re,shutil,sys,json,hashlib
ROOT=Path(__file__).resolve().parent

def install(root):
 if not (root/'workspace'/'index.html').is_file():raise ValueError('Extract beside the existing workspace folder, not inside it.')
 js=(ROOT/'default_filters.js').read_text(encoding='utf-8')
 pages=[]
 for folder in [root,root/'workspace']:
  for name in ['index.html','index_v0_4.html']:
   if (folder/name).is_file():pages.append(folder/name)
 history=root/'history_views'
 if history.is_dir():
  pages += [p for p in history.rglob('*.html') if p.name in ('index.html','index_v0_4.html') and not any(x.startswith('.pending_') for x in p.parts)]
 protected=[p for p in (root/'workspace').iterdir() if p.is_file() and p.suffix in ('.js','.css','.gz','.json')]
 digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 before={str(p):digest(p) for p in protected};updates=[]
 for page in pages:
  text=page.read_text(encoding='utf-8-sig')
  if 'id="pnl-default-filters-v1"' in text:continue
  if not re.search(r'</body\s*>',text,re.I):raise ValueError('Missing closing body in '+str(page))
  backup=page.with_name(page.name+'.before_default_filters')
  if not backup.exists():shutil.copy2(page,backup)
  updated=re.sub(r'</body\s*>',lambda m:'\n<script id="pnl-default-filters-v1">\n'+js+'\n</script>\n'+m.group(),text,count=1,flags=re.I)
  page.write_text(updated,encoding='utf-8');updates.append(str(page))
 after={str(p):digest(p) for p in protected}
 if before!=after:raise RuntimeError('Protected files changed concurrently. Stop other builds before retrying.')
 (root/'default_filters_install.json').write_text(json.dumps({'updatedPages':updates,'dataAndCoreUnchanged':before==after,'protectedHashes':before},indent=2))
 print('Installed default filters on '+str(len(updates))+' pages. Reload the dashboard. No reimport or republish required.')
 return updates
if __name__=='__main__':
 try:install(ROOT)
 except Exception as e:print('NOT APPLIED: '+str(e),file=sys.stderr);sys.exit(1)
