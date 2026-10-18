"""Validated, checksummed layer cache; atomic publish and per-key process lock."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import os


def key_of(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


@contextmanager
def key_lock(root, key):
    folder = Path(root)/'.locks'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/(key+'.lock')
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('同一缓存任务已运行，或上次中断遗留锁；请确认进程已退出后手动移除对应 .lock') from None
    try:
        os.write(fd, json.dumps({'pid': os.getpid(), 'started': time.time()}).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def cached_layer(root, identity, producer):
    root = Path(root)
    key = key_of(identity)
    target = root/key
    with key_lock(root, key):
        try:
            manifest = json.loads((target/'layer.json').read_text('utf-8'))
            files = manifest['files']
            if manifest['identity'] == identity and isinstance(files, dict) and files and all(
                Path(name).name == name and (target/name).is_file() and digest(target/name) == value for name, value in files.items()):
                return target, True
        except (OSError, ValueError, KeyError, TypeError):
            pass
        stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=root))
        backup = None
        try:
            producer(stage)
            files = {p.name: digest(p) for p in stage.iterdir() if p.is_file() and p.name != 'layer.json'}
            if not files:
                raise ValueError('Empty layer result')
            (stage/'layer.json').write_text(json.dumps({'identity': identity, 'files': files}, ensure_ascii=False), 'utf-8')
            if target.exists():
                backup = root/('.previous-'+key+'-'+str(time.time_ns()))
                target.rename(backup)
            try:
                stage.rename(target)
            except OSError:
                if backup:
                    backup.rename(target)
                raise
            return target, False
        finally:
            if stage.exists():
                shutil.rmtree(stage)
