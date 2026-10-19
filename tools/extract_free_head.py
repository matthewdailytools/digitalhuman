"""Extract the verified vendor package without allowing archive paths to escape."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

PROJECT = Path(__file__).resolve().parents[1]


def safe_destination(root, member):
    name = member.filename.replace(chr(92), '/')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or any(':' in part for part in path.parts):
        raise ValueError('Unsafe path in asset archive')
    if stat.S_ISLNK(member.external_attr >> 16):
        raise ValueError('Asset archive contains a symbolic link')
    target = (root / Path(*path.parts)).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Asset archive path escapes destination')
    return target


def extract(archive_path, output):
    archive_path, output = Path(archive_path).resolve(), Path(output).resolve()
    inventory = json.loads(archive_path.with_suffix('.inventory.json').read_text('utf-8'))
    with archive_path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != inventory['sha256']:
            raise ValueError('Archive changed after checksum verification')
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        paths = [(member, safe_destination(output, member)) for member in archive.infolist()]
        for member, destination in paths:
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ValueError('Extraction destination already contains files; original asset was not overwritten')
            with archive.open(member) as source, destination.open('xb') as target:
                while chunk := source.read(4 * 1024**2):
                    target.write(chunk)
    report = dict(archive_sha256=inventory['sha256'], output=str(output),
                  blend_files=[str(p) for p in output.rglob('*.blend')],
                  obj_files=[str(p) for p in output.rglob('*.obj')],
                  fbx_files=[str(p) for p in output.rglob('*.fbx')],
                  file_count=sum(1 for p in output.rglob('*') if p.is_file()))
    (output.parent / 'extracted.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', default=str(PROJECT / '.cache/assets/3dscanstore/free-head.zip'))
    parser.add_argument('--output', default=str(PROJECT / '.cache/assets/3dscanstore/original'))
    args = parser.parse_args()
    extract(args.archive, args.output)
