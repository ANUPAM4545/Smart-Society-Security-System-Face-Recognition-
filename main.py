"""Command-line entry point. Run python main.py --help."""
import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path
from security.core import Database, match
from security.evaluation import build_report, save_report

ROOT = Path(__file__).resolve().parent


def evaluate(db, manifest, threshold, output):
    from security.vision import image_encoding
    manifest = Path(manifest).resolve()
    gallery = db.gallery()
    ids = {r[0] for r in gallery}
    if not ids:
        raise ValueError('Enroll residents before evaluation.')
    trials = []
    with manifest.open(newline='', encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if not {'image', 'expected_id'} <= set(reader.fieldnames or []):
            raise ValueError('CSV needs image and expected_id columns.')
        for line_number, row in enumerate(reader, start=2):
            if row.get('image') is None or row.get('expected_id') is None or None in row or not row['image'].strip():
                raise ValueError(f'Malformed CSV row {line_number}: image and expected_id fields are required.')
            expected = row['expected_id'].strip() or None
            if expected is not None and expected not in ids:
                raise ValueError('Unknown/inactive expected_id: ' + expected)
            path = manifest.parent / row['image']
            encoding = image_encoding(path)
            result = match(encoding, gallery, threshold)
            trials.append(dict(image=row['image'], expected_id=expected, **result))
    if not trials:
        raise ValueError('Evaluation manifest is empty.')
    report = build_report(trials, threshold, ids)
    output = Path(output)
    save_report(report, output)
    print(json.dumps(report['metrics'],indent=2))
    print('Reports saved to',output.resolve())


def main():
    parser = argparse.ArgumentParser(description='Smart Society Security | Face Recognition')
    parser.add_argument('--db', default=str(ROOT/'data'/'society.db'))
    sub = parser.add_subparsers(dest='command',required=True)
    register = sub.add_parser('register',help='Enroll one resident from webcam or photos')
    register.add_argument('--id',required=True)
    register.add_argument('--name',required=True)
    register.add_argument('--apartment',required=True)
    register.add_argument('--images',nargs='+',help='Single-person JPG/PNG images')
    register.add_argument('--camera',type=int,default=0)
    register.add_argument('--samples',type=int,default=5)
    monitor = sub.add_parser('monitor',help='Open live webcam entry monitor; Q exits')
    monitor.add_argument('--camera',type=int,default=0)
    monitor.add_argument('--threshold',type=float,default=0.48)
    sub.add_parser('residents',help='List enrollment progress and resident IDs')
    for name in ('deactivate','activate'):
        p = sub.add_parser(name)
        p.add_argument('id')
    logs = sub.add_parser('logs',help='View or export entry logs')
    logs.add_argument('--csv',help='Export path')
    ev = sub.add_parser('evaluate',help='Calculate measured metrics from held-out photos')
    ev.add_argument('manifest')
    ev.add_argument('--threshold',type=float,default=0.48)
    ev.add_argument('--output',default=str(ROOT/'reports'))
    args = parser.parse_args()
    if hasattr(args,'threshold') and not 0 < args.threshold < 1:
        parser.error('--threshold must be between 0 and 1')
    db = Database(args.db)
    try:
        if args.command == 'register':
            if not 1 <= args.samples <= 30:
                raise ValueError('--samples must be 1 through 30')
            from security.vision import capture, image_encoding, validate_samples
            samples = [image_encoding(p) for p in args.images] if args.images else capture(args.camera,args.samples)
            validate_samples(samples)
            db.enroll(args.id,args.name,args.apartment,samples)
            print(f'Registered {args.name}: {len(samples)} samples saved.')
        elif args.command == 'monitor':
            from security.vision import monitor
            monitor(db,args.camera,args.threshold)
        elif args.command == 'residents':
            rows = db.residents()
            print(json.dumps(rows,indent=2))
            count = sum(bool(r['active'] and r['samples']) for r in rows)
            print(f'Assignment progress: {count}/20 active residents')
        elif args.command in ('activate','deactivate'):
            db.set_active(args.id,args.command == 'activate')
            print('Resident status updated. Restart a running monitor to reload the gallery.')
        elif args.command == 'logs':
            rows = db.events()
            if args.csv:
                with open(args.csv,'w',newline='',encoding='utf-8') as handle:
                    writer = csv.DictWriter(handle,fieldnames=['id','timestamp','resident_id','decision','distance','reason'])
                    writer.writeheader()
                    writer.writerows(rows)
                print('Exported',args.csv)
            else:
                print(json.dumps(rows,indent=2))
        elif args.command == 'evaluate':
            evaluate(db,args.manifest,args.threshold,args.output)
    except ImportError as exc:
        print(f'Missing dependency: {exc}. Install requirements.txt in your virtual environment.',file=sys.stderr)
        return 1
    except (ValueError,OSError,sqlite3.Error) as exc:
        print('Error:',exc,file=sys.stderr)
        return 1
    finally:
        db.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
