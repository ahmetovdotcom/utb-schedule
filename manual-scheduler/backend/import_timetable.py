"""Copy reference data from a read-only timetable-system SQLite snapshot.
Run: .venv/bin/python import_timetable.py SOURCE.sqlite [--dry-run]
Existing lessons and reference IDs are preserved; repeated runs are idempotent.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import main


def read_records(path):
    source = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    try:
        tables = {name: [dict(r) for r in source.execute('SELECT * FROM '+name)] for name in ['departments','buildings','rooms','teachers','student_groups','subjects']}
    finally:
        source.close()
    departments = {r['id']:r['name'] for r in tables['departments']}
    buildings = {r['id']:r['name'] for r in tables['buildings']}
    result=[]
    for kind, table, name_field in [('departments','departments','name'),('buildings','buildings','name'),('rooms','rooms','number'),('teachers','teachers','full_name'),('groups','student_groups','code'),('subjects','subjects','name')]:
        names=Counter(str(r[name_field]).strip() for r in tables[table])
        used=set()
        for row in tables[table]:
            name=str(row[name_field]).strip()
            department=departments.get(row.get('department_id'),'')
            fields={'department':department}
            if kind=='rooms':
                fields.update(capacity=row['capacity'],building=buildings[row['building_id']],room_type=row['room_type'])
                name=f"{fields['building']} / {name}"
            elif kind=='groups':
                fields.update(students=row['students_count'],course=row['course'])
                if names[name]>1: name=f"{name} · {row['course']} курс"
            if name in used: name=f"{name} · #{row['id']}"
            used.add(name)
            value=main.Reference(name=name,**fields).model_dump()
            label=value.pop('name')
            value.update(source='timetable-system',source_table=table,source_id=row['id'])
            result.append((kind,label,value))
    return result


def import_records(path,dry_run=False):
    records=read_records(Path(path))  # validate everything before touching the target
    counts=Counter(kind for kind,_,_ in records)
    if dry_run:return {'source':dict(counts)}
    backup=None
    if main.DB.exists():
        folder=main.DB.parent/'backups';folder.mkdir(exist_ok=True)
        backup=folder/('before-reference-import-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite')
        with sqlite3.connect(main.DB.resolve().as_uri()+'?mode=ro',uri=True) as src, sqlite3.connect(backup) as dst:
            src.backup(dst)
    created=updated=0
    with main.database(True) as con:
        existing=main.refs(con)
        origin={(r.get('source_table'),r.get('source_id')):r for r in existing.values() if r.get('source')=='timetable-system'}
        names={(r['kind'],r['name']):r for r in existing.values()}
        for kind,name,data in records:
            previous=origin.get((data['source_table'],data['source_id'])) or names.get((kind,name))
            if previous:
                con.execute('UPDATE refs SET name=?,data=? WHERE id=?',(name,json.dumps(data,ensure_ascii=False),previous['id']))
                updated+=1
            else:
                con.execute('INSERT INTO refs(kind,name,data) VALUES(?,?,?)',(kind,name,json.dumps(data,ensure_ascii=False)))
                created+=1
    return {'source':dict(counts),'created':created,'updated':updated,'backup':str(backup) if backup else None}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    print(json.dumps(import_records(args.source,args.dry_run),ensure_ascii=False,indent=2))
