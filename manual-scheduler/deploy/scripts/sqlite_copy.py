"""Consistent SQLite snapshot; never replaces an existing destination."""
import argparse
import os
from pathlib import Path
import sqlite3
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('destination', type=Path)
parser.add_argument('--uid', type=int)
parser.add_argument('--gid', type=int)
args = parser.parse_args()
if not args.source.is_file():
    parser.error('Source database does not exist')
if args.destination.exists():
    parser.error('Destination already exists; refusing to overwrite it')
args.destination.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(dir=args.destination.parent, suffix='.sqlite')
os.close(fd)
try:
    with sqlite3.connect(args.source.resolve().as_uri() + '?mode=ro', uri=True) as source:
        with sqlite3.connect(temporary) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database integrity check failed')
    os.chmod(temporary, 0o600)
    if args.uid is not None:
        os.chown(temporary, args.uid, args.gid if args.gid is not None else args.uid)
    os.link(temporary, args.destination)  # Fails safely if the destination appeared meanwhile.
finally:
    os.unlink(temporary)
print('Database snapshot saved.')
