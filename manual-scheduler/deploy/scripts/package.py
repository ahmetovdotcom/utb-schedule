"""Package manual-scheduler and UTB2, excluding state and credentials."""
from datetime import datetime, timezone
from pathlib import Path
import tarfile
root = Path(__file__).resolve().parents[3]
folder = root/'manual-scheduler/deploy/releases'
folder.mkdir(exist_ok=True)
output = folder/('okak-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.tar.gz')
excluded = {'node_modules','.git','.venv','venv','__pycache__','dist','backups','releases','.DS_Store'}
with tarfile.open(output,'w:gz') as archive:
    for name in ('README.md','deploy.sh'):
        archive.add(root/name,arcname=name,recursive=False)
    for project in ('manual-scheduler','UTB2'):
        for path in sorted((root/project).rglob('*')):
            if not path.is_file() or path.is_symlink():continue
            if any(part in excluded for part in path.relative_to(root).parts):continue
            if path.name.startswith('.env') and path.name!='.env.example':continue
            if path.suffix in {'.pyc','.db','.sqlite','.sqlite3','.dump','.log','.credentials'}:continue
            if any(s in path.name for s in ('.db-','.sqlite-','.sqlite3-')):continue
            archive.add(path,arcname=str(path.relative_to(root)),recursive=False)
print(output)
