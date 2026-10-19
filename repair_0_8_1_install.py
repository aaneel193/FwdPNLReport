#!/usr/bin/env python3
"""Install/restore 0.8.1 without changing archive, workspace, or selections."""
from pathlib import Path
import sys, subprocess, shutil, datetime, os, json, importlib.util, re
ROOT = Path(__file__).resolve().parent
TARGET = ROOT/'local_date_app.py'
CANDIDATE = ROOT/'local_date_app_0_8_1.py'
REPORT = ROOT/'REPAIR_0_8_1_INSTALL_LOG.txt'
BACKUP_RECORD = ROOT/'REPAIR_0_8_1_BACKUP.txt'
def main():
    if len(sys.argv)>1 and sys.argv[1]=='restore':
        backup=ROOT/BACKUP_RECORD.read_text(encoding='utf-8').strip()
        if backup.parent != ROOT or not backup.is_file(): raise ValueError('Valid rollback copy missing.')
        compile(backup.read_text(encoding='utf-8-sig'),str(backup),'exec')
        shutil.copy2(backup,TARGET)
        print('Restored',backup.name); return 0
    if not TARGET.is_file(): raise ValueError('Place these files beside the existing local_date_app.py.')
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup=ROOT/('local_date_app_BEFORE_0_8_1_'+stamp+'.py')
    shutil.copy2(TARGET,backup)
    BACKUP_RECORD.write_text(backup.name,encoding='utf-8')
    print('Backup:',backup.name)
    compile(CANDIDATE.read_text(encoding='utf-8-sig'),str(CANDIDATE),'exec')
    # Validate the candidate in the real project folder BEFORE replacing TARGET.
    result=subprocess.run([sys.executable,str(CANDIDATE),'--check'],cwd=ROOT,
                          capture_output=True,text=True)
    REPORT.write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    print(result.stdout); print(result.stderr)
    if result.returncode:
        print('NOT INSTALLED. Existing local_date_app.py was left unchanged.')
        print('See',REPORT.name)
        return 1
    # Separately parse generated JavaScript when Node is available locally.
    node=shutil.which('node')
    if node:
        spec=importlib.util.spec_from_file_location('repair_candidate',CANDIDATE)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        mod.PAGE_NAME='index_v0_4.html' if (ROOT/'workspace'/'index_v0_4.html').exists() else 'index.html'
        scripts=[mod.CLIENT_JS,mod.build_served_core().decode('utf-8')]
        scripts += [m.group(1) for m in re.finditer(r'<script\b[^>]*>(.*?)</script\s*>',mod.build_served_html().decode('utf-8'),re.I|re.S) if m.group(1).strip()]
        for i,js in enumerate(scripts):
            temp=ROOT/('repair_0_8_1_check_'+stamp+'_'+str(i)+'.js')
            try:
                temp.write_text(js,encoding='utf-8')
                check=subprocess.run([node,'--check',str(temp)],capture_output=True,text=True)
                if check.returncode: raise ValueError('JavaScript check failed: '+check.stderr)
            finally: temp.unlink(missing_ok=True)
        print('Generated JavaScript syntax checks passed.')
    else:
        print('Node not found: local JavaScript parsing skipped; browser validation still required.')
    temporary=ROOT/('local_date_app_0_8_1_install_'+stamp+'.tmp')
    try:
        shutil.copy2(CANDIDATE,temporary);os.replace(temporary,TARGET)
    finally: temporary.unlink(missing_ok=True)
    print('INSTALLED 0.8.1. Start using the existing launcher.')
    print('Acceptance still requires source-count and financial reconciliation.')
    return 0
if __name__=='__main__':
    try: sys.exit(main())
    except Exception as error:
        print('STOPPED:',error)
        print('Existing app is not replaced unless all candidate checks pass.')
        sys.exit(1)
