import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from tools.extract_free_head import extract
from static_head import cached, FILES


class ScanAssetTests(unittest.TestCase):
    def archive(self,root,name,symlink=False):
        path=root/'sample.zip'
        with zipfile.ZipFile(path,'w') as archive:
            member=zipfile.ZipInfo(name)
            if symlink:member.external_attr=(stat.S_IFLNK|0o777)<<16
            archive.writestr(member,b'isolated-test-fixture')
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        path.with_suffix('.inventory.json').write_text(json.dumps({'sha256':sha}),'utf-8')
        return path

    def test_untrusted_archive_paths_and_symlinks_cannot_escape_or_extract(self):
        for name,symlink in (('../outside.txt',False),('C:/outside.txt',False),
                             ('folder/../../outside.txt',False),('link',True)):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                path=self.archive(root,name,symlink)
                with self.assertRaises(ValueError):extract(path,root/'original')
                self.assertFalse((root/'outside.txt').exists())
                self.assertFalse(any((root/'original').rglob('*')))

    def test_archive_change_or_existing_original_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            path=self.archive(root,'Blender/scene.blend')
            extract(path,root/'original')
            original=root/'original/Blender/scene.blend'
            original.write_bytes(b'user-preserved-file')
            with self.assertRaises(ValueError):extract(path,root/'original')
            self.assertEqual(original.read_bytes(),b'user-preserved-file')
            path.write_bytes(path.read_bytes()+b'tamper')
            with self.assertRaises(ValueError):extract(path,root/'other')
            self.assertFalse((root/'other').exists())

    def test_changed_or_incomplete_static_cache_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            identity={'asset':'isolated-test-fixture'}
            hashes={}
            for name in FILES:
                (root/name).write_bytes(b'fixture')
                hashes[name]=hashlib.sha256(b'fixture').hexdigest()
            (root/'manifest.json').write_text(json.dumps(dict(identity=identity,files=hashes)),'utf-8')
            self.assertTrue(cached(root,identity))
            self.assertFalse(cached(root,{'asset':'different'}))
            (root/'front.png').write_bytes(b'changed')
            self.assertFalse(cached(root,identity))
            hashes['../outside.txt']='irrelevant'
            (root/'manifest.json').write_text(json.dumps(dict(identity=identity,files=hashes)),'utf-8')
            self.assertFalse(cached(root,identity))


if __name__=='__main__':unittest.main()
