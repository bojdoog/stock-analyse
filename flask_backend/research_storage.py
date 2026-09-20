"""Lossless database archive of research CSV and MCP JSON inputs."""
import base64
import hashlib
import json
from pathlib import Path

from market_store import PROJECT, file_content
from resilient_store import import_source


def archive_key(path):
    relative = Path(path).resolve().relative_to(PROJECT / 'back_test_data').as_posix()
    return relative, 'research/' + hashlib.sha256(relative.encode('utf-8')).hexdigest() + '.json'


def archive_file(path):
    relative, key = archive_key(path)
    payload = json.dumps({'path': relative, 'base64': base64.b64encode(Path(path).read_bytes()).decode('ascii')},
                         ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    import_source(key, payload)


def read_file(path):
    _, key = archive_key(path)
    content = file_content(key, 'auto')
    if content is not None:
        return base64.b64decode(json.loads(content)['base64'])
    return Path(path).read_bytes() if Path(path).exists() else None
