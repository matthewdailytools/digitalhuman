"""Resumable parallel download of the official personal-use-only head sample."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.request import build_opener, ProxyHandler, Request
from zipfile import ZipFile

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www.3dscanstore.com/blog/Free-3D-Head-Model'
URL = 'https://samplescan.s3.us-west-2.amazonaws.com/3D_ScanStore_Free+Head.zip'
TRANSPORT_URL = 'https://samplescan.s3-us-west-2.amazonaws.com/3D_ScanStore_Free+Head.zip'


def download(output, proxy, connections):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    def opener():
        return build_opener(ProxyHandler({'http': proxy, 'https': proxy} if proxy else {}))
    with opener().open(Request(TRANSPORT_URL, method='HEAD'), timeout=30) as response:
        size, etag = int(response.headers['Content-Length']), response.headers['ETag']
    manifest = output.with_suffix('.download.json')
    identity = dict(url=URL, size=size, etag=etag, connections=connections)
    if manifest.exists() and json.loads(manifest.read_text('utf-8')) != identity:
        raise ValueError('Download identity changed; choose a new output path')
    manifest.write_text(json.dumps(identity, indent=2), 'utf-8')
    if not output.is_file():
        lock, started = threading.Lock(), time.monotonic()
        counts = [0] * connections
        resumed = sum(output.with_suffix(f'.part{i:02d}').stat().st_size
                      for i in range(connections) if output.with_suffix(f'.part{i:02d}').exists())
        stop = threading.Event()
        def progress():
            while not stop.wait(10):
                with lock:
                    done = sum(counts)
                seconds = time.monotonic() - started
                print(f'DOWNLOAD {done}/{size} bytes ({done/size:.1%}); new data {(done-resumed)/max(seconds,1)/1024**2:.2f} MiB/s', flush=True)
        reporter = threading.Thread(target=progress, daemon=True)
        reporter.start()
        def part(index):
            start, end = size * index // connections, size * (index + 1) // connections - 1
            path = output.with_suffix(f'.part{index:02d}')
            existing = path.stat().st_size if path.exists() else 0
            length = end - start + 1
            if existing > length:
                raise ValueError('Oversized partial download')
            counts[index] = existing
            failures = 0
            while True:
                existing = path.stat().st_size if path.exists() else 0
                if existing == length:
                    return path
                position = start + existing
                request_end = min(end, position + 16 * 1024**2 - 1)
                request = Request(TRANSPORT_URL, headers={'Range': f'bytes={position}-{request_end}'})
                try:
                    with opener().open(request, timeout=12) as response, path.open('ab') as stream:
                        expected = f'bytes {position}-{request_end}/{size}'
                        if response.status != 206 or response.headers.get('Content-Range') != expected:
                            raise ValueError('Server did not honor the requested byte range')
                        if response.headers.get('ETag') != etag:
                            raise ValueError('Source changed during download')
                        requested_at, received = time.monotonic(), 0
                        while chunk := response.read(8 * 1024):
                            stream.write(chunk)
                            received += len(chunk)
                            with lock:
                                counts[index] += len(chunk)
                            elapsed = time.monotonic() - requested_at
                            if elapsed > 4 and received / elapsed < 128 * 1024:
                                raise TimeoutError('Slow range; reconnecting with partial bytes preserved')
                    if path.stat().st_size != request_end - start + 1:
                        raise OSError('Incomplete download range')
                    failures = 0
                except (OSError, TimeoutError):
                    failures += 1
                    if failures >= 100:
                        raise
                    time.sleep(1)
        try:
            with ThreadPoolExecutor(max_workers=connections) as pool:
                paths = list(pool.map(part, range(connections)))
            merged = output.with_suffix('.joining')
            with merged.open('wb') as destination:
                for path in paths:
                    with path.open('rb') as source:
                        while chunk := source.read(4 * 1024**2):
                            destination.write(chunk)
            if merged.stat().st_size != size:
                raise ValueError('Merged download has the wrong size')
            merged.replace(output)
            for path in paths:
                path.unlink()
        finally:
            stop.set()
            reporter.join(timeout=1)
    if output.stat().st_size != size:
        raise ValueError('Downloaded archive size mismatch')
    print('DOWNLOAD COMPLETE; validating ZIP checksums', flush=True)
    with ZipFile(output) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError('Archive checksum validation failed')
        entries = [dict(name=x.filename, size=x.file_size) for x in archive.infolist()]
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = dict(source_page=SOURCE, download_url=URL, transport_url=TRANSPORT_URL,
                  license='Personal use only; contact vendor for commercial use',
                  archive=str(output), size=size, sha256=digest, zip_crc_verified=True, entries=entries)
    output.with_suffix('.inventory.json').write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'entries'}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(PROJECT / '.cache/assets/3dscanstore/free-head.zip'))
    parser.add_argument('--proxy', default='http://127.0.0.1:7900')
    parser.add_argument('--connections', type=int, choices=range(1,9), default=6)
    args = parser.parse_args()
    download(args.output, args.proxy, args.connections)
