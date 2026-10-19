"""Add narrow, backed-up download rules to the active Clash Verge subscription.

Requires PyYAML. Credentials and subscription content never enter reports or Git.
"""
from datetime import datetime
import http.client
import json
import os
from pathlib import Path
import shutil
import subprocess

import yaml

PROJECT = Path(__file__).resolve().parents[1]
DOMAINS = ('www.3dscanstore.com', '3dscanstore.com', 'samplescan.s3.us-west-2.amazonaws.com',
           'samplescan.s3-us-west-2.amazonaws.com')
RULES = ['DOMAIN,' + domain + ',DIRECT' for domain in DOMAINS]


class PipeSocket:
    def __init__(self, path):
        self.stream = open(path, 'r+b', buffering=0)

    def sendall(self, data):
        view = memoryview(data)
        while view:
            count = self.stream.write(view)
            if not count:
                raise OSError('Local controller write failed')
            view = view[count:]

    def makefile(self, *args, **kwargs):
        return self.stream

    def close(self):
        self.stream.close()


def controller(config, method, endpoint, data=None):
    name = config['external-controller-pipe'].split(chr(92))[-1]
    prefix = chr(92) * 2 + '.' + chr(92) + 'pipe' + chr(92)
    candidates = (name, name.replace('sidecar-release', 'production'))
    sock = None
    for candidate in dict.fromkeys(candidates):
        try:
            sock = PipeSocket(prefix + candidate)
            break
        except FileNotFoundError:
            continue
    if sock is None:
        raise RuntimeError('Clash local controller pipe not found')
    conn = http.client.HTTPConnection('localhost', timeout=20)
    conn.sock = sock
    try:
        headers = {'Authorization': 'Bearer ' + config.get('secret', '')}
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        conn.request(method, endpoint, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        if response.status not in (200, 204):
            raise RuntimeError(f'Clash controller HTTP {response.status}')
        return json.loads(raw) if raw else {}
    finally:
        conn.close()


def prepend(existing):
    return RULES + [rule for rule in existing if rule not in RULES]


def main():
    root = Path(os.environ['APPDATA']) / 'io.github.clash-verge-rev.clash-verge-rev'
    profiles = yaml.safe_load((root / 'profiles.yaml').read_text('utf-8-sig'))
    active = next(x for x in profiles['items'] if x['uid'] == profiles['current'])
    uid = active['option']['rules']
    item = next(x for x in profiles['items'] if x['uid'] == uid)
    rules_path = root / 'profiles' / item['file']
    runtime_path = root / 'clash-verge.yaml'
    originals = {path: path.read_bytes() for path in (rules_path, runtime_path)}
    rules = yaml.safe_load(originals[rules_path].decode('utf-8-sig'))
    config = yaml.safe_load(originals[runtime_path].decode('utf-8-sig'))
    if controller(config, 'GET', '/configs').get('mode') != 'rule':
        raise RuntimeError('Clash must be in rule mode; existing mode was not changed')
    rules['prepend'] = prepend(rules.get('prepend', []))
    config['rules'] = prepend(config.get('rules', []))
    backup = PROJECT / 'work/local-config-backups' / ('clash-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, exist_ok=False)
    for path in originals:
        shutil.copy2(path, backup / path.name)
    candidate = backup / 'candidate.yaml'
    rendered = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    candidate.write_text(rendered, 'utf-8')
    executable = Path(os.environ['ProgramFiles']) / 'Clash Verge/verge-mihomo.exe'
    check = subprocess.run([str(executable), '-t', '-d', str(root), '-f', str(candidate)],
                           capture_output=True, timeout=30,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if check.returncode:
        raise RuntimeError('Clash candidate validation failed; configuration unchanged')
    try:
        rules_path.write_text(yaml.safe_dump(rules, allow_unicode=True, sort_keys=False), 'utf-8')
        runtime_path.write_text(rendered, 'utf-8')
        controller(config, 'PUT', '/configs?force=true', {'payload': rendered})
        actual = controller(config, 'GET', '/rules')['rules']
        matched = [rule for rule in actual if rule.get('type') == 'Domain'
                   and rule.get('payload') in DOMAINS and rule.get('proxy') == 'DIRECT']
        if len(matched) != len(DOMAINS):
            raise RuntimeError('Clash active rule verification failed')
    except Exception:
        for path, content in originals.items():
            path.write_bytes(content)
        controller(config, 'PUT', '/configs?force=true',
                   {'payload': originals[runtime_path].decode('utf-8-sig')})
        raise
    finally:
        candidate.unlink(missing_ok=True)
    report = dict(success=True, rules=RULES, active_rules_verified=True,
                  subscription_rules_path=str(rules_path), backup_path=str(backup))
    (backup / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
