"""Explicit inventory and removal of superseded video entries only."""
from pathlib import Path
import re
import shutil

PATTERN=re.compile(r'^[0-9a-f]{64}\.previous-[0-9a-f]{32}$')


def inventory(root):
    root=Path(root)
    entries=[]
    if root.exists():
        for folder in root.iterdir():
            if folder.is_dir() and not folder.is_symlink() and (re.fullmatch('[0-9a-f]{64}',folder.name) or PATTERN.fullmatch(folder.name)):
                entries.append(dict(name=folder.name,bytes=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file() and not p.is_symlink()), previous=bool(PATTERN.fullmatch(folder.name))))
    return entries


def clean_previous(root):
    root=Path(root).resolve()
    removed=0
    for item in inventory(root):
        if not item['previous']:
            continue
        path=root/item['name']
        if path.is_symlink() or path.resolve().parent != root or any(p.is_symlink() for p in path.rglob('*')):
            raise ValueError('拒绝清理包含符号链接的缓存')
        shutil.rmtree(path)
        removed+=item['bytes']
    return removed
