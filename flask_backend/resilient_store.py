"""Durable local writes, replay to MySQL, and automatic read fallback.

SQLite and its pending queue commit together. MySQL replay is idempotent, so a
crash after the remote commit is safe to retry. Explicit database paths bypass
this policy for migrations and isolated tests.
"""
import logging
import os
import time
from pathlib import Path

import market_store as store

logger = logging.getLogger(__name__)
_retry_at = 0.0
_initialized = set()


def sqlite_path():
    return Path(os.environ.get('SQLITE_DATABASE_PATH') or store.DEFAULT_DATABASE).resolve()


def local_initialize():
    path = sqlite_path()
    if path in _initialized and path.exists():
        return
    store.initialize(path)
    with store.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS mysql_pending(path TEXT PRIMARY KEY REFERENCES source_files(path))')
        db.commit()
    _initialized.add(path)


def unavailable(exc):
    if isinstance(exc, (ImportError, OSError)):
        return True
    if isinstance(exc, RuntimeError) and 'cryptography' in str(exc) and 'auth' in str(exc):
        return True
    try:
        import pymysql
    except ImportError:
        return False
    return isinstance(exc, (pymysql.OperationalError, pymysql.InterfaceError)) and (
        not exc.args or exc.args[0] in (0, 1040, 1044, 1045, 1049, 1129, 1130, 1142, 1203,
                                      1226, 2002, 2003, 2006, 2013, 2026, 2055, 2059, 2061))


def offline(exc):
    global _retry_at
    _retry_at = time.monotonic() + 30
    # Never log connection arguments or passwords.
    logger.warning('MySQL unavailable (%s); using SQLite. Pending writes will retry after 30 seconds.', type(exc).__name__)


def replay(remote):
    local_initialize()
    with store.connect(sqlite_path()) as local:
        if not local.execute('SELECT 1 FROM mysql_pending LIMIT 1').fetchone():
            return
        local.execute('BEGIN IMMEDIATE')
        try:
            # Keep the local writer lock until replay finishes, preventing stale
            # snapshots from replacing a newer fetch on another process.
            pending = local.execute('SELECT path FROM mysql_pending ORDER BY path').fetchall()
            for row in pending:
                content = local.execute('SELECT content FROM source_files WHERE path=?', (row['path'],)).fetchone()[0]
                store.import_content(remote, row['path'], content)
                local.execute('DELETE FROM mysql_pending WHERE path=?', (row['path'],))
            local.commit()
        except Exception:
            local.rollback()
            raise


def try_mysql():
    if time.monotonic() < _retry_at:
        return None
    remote = None
    try:
        remote = store.open_connection('mysql')
        # A recreated database must not silently serve an empty subset.
        if not remote.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='source_files'").fetchone():
            remote.close()
            logger.warning('MySQL market tables missing; using SQLite. Restore MySQL before switching back.')
            return None
        replay(remote)
        return remote
    except Exception as exc:
        if remote is not None:
            remote.close()
        if not unavailable(exc):
            raise
        offline(exc)
        return None


def open_connection():
    local_initialize()
    remote = try_mysql()
    return remote if remote is not None else store.open_connection(sqlite_path())


def initialize():
    local_initialize()
    remote = try_mysql()
    if remote is not None:
        remote.close()


def save_dataframe(frame, output_path, category=None):
    local_initialize()
    store.save_dataframe(frame, output_path, sqlite_path(), category, _pending=True)
    remote = try_mysql()
    if remote is not None:
        remote.close()


def import_source(relative_path, content, export_path=None):
    """Import an exact snapshot and export it through the same durable queue."""
    local_initialize()
    with store.connect(sqlite_path()) as db:
        db.execute('BEGIN IMMEDIATE')
        changed = store.import_content(db, relative_path, content, pending=True)
        db.commit()
        if export_path is not None:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT content FROM source_files WHERE path=?', (relative_path,)).fetchone()[0]
            export_path = Path(export_path)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_bytes(current)
            db.commit()
    remote = try_mysql()
    if remote is not None:
        remote.close()
    return changed


def refresh_index(out_dir, category=None):
    import json
    local_initialize()
    out_dir = Path(out_dir)
    category = category or out_dir.name
    with store.connect(sqlite_path()) as db:
        db.execute('BEGIN IMMEDIATE')
        files = [row[0].split('/')[-1] for row in db.execute(
            "SELECT path FROM source_files WHERE category=? AND path LIKE '%.csv' ORDER BY path", (category,))]
        content = json.dumps(files, ensure_ascii=False).encode('utf-8')
        store.import_content(db, f'{category}/index.json', content, pending=True)
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        content = db.execute('SELECT content FROM source_files WHERE path=?', (f'{category}/index.json',)).fetchone()[0]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / 'index.json').write_bytes(content)
        db.commit()
    remote = try_mysql()
    if remote is not None:
        remote.close()
    return files
