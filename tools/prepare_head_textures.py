"""Create lossless 2K texture proxies; the downloaded original files stay untouched."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(original, output, maximum):
    original, output = Path(original).resolve(), Path(output).resolve()
    if output == original or output.is_relative_to(original):
        raise ValueError('Proxy output must be outside the original asset directory')
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for source in sorted((original / 'Textures/JPG').rglob('*.jpg')):
        target = output / source.relative_to(original / 'Textures/JPG').with_suffix('.png')
        target.parent.mkdir(parents=True, exist_ok=True)
        source_hash = digest(source)
        with Image.open(source) as image:
            original_size = image.size
            image.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
            image.save(target, 'PNG', compress_level=3)
            resized = image.size
        entries.append(dict(name=source.name, source=str(source), source_sha256=source_hash,
                            proxy=str(target), proxy_sha256=digest(target),
                            original_size=original_size, proxy_size=resized))
        print('TEXTURE', source.name, original_size, '->', resized, flush=True)
    if not entries:
        raise ValueError('No original JPG textures found')
    report = dict(original=str(original), maximum=maximum, entries=entries,
                  note='Lossless PNG proxies of the vendor JPGs; no original asset was overwritten')
    (output / 'textures.json').write_text(json.dumps(report, indent=2), 'utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--original', default=str(PROJECT / '.cache/assets/3dscanstore/original'))
    parser.add_argument('--output', default=str(PROJECT / 'work/realistic-head/textures-2k'))
    parser.add_argument('--maximum', type=int, choices=(1024,2048,4096), default=2048)
    args=parser.parse_args()
    prepare(args.original,args.output,args.maximum)
