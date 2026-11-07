"""页面控制台任务：把耗时操作放到后台线程，前端轮询日志与进度。"""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_LIMIT = 5000

_jobs = {}
_lock = threading.Lock()


class Job:
    def __init__(self, kind, title, options=None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.title = title
        self.options = options or {}
        self.status = 'running'
        self.progress = 0
        self.logs = []
        self.started = time.time()
        self.result = None
        self.cancelled = False
        self.proc = None
        self.wait = None  # 限流等待：{'left': 剩余秒数, 'total': 总秒数}
        self.stage = None  # 当前阶段：下载 / 入库
        self.stage_percent = 0  # 当前阶段进度（0-100），供控制台里的进度条渲染
        self.stage_done = 0  # 当前阶段已完成数量
        self.stage_total = 0  # 当前阶段总数
        self.rate_limit_hits = 0

    def log(self, message):
        with _lock:
            if len(self.logs) < LOG_LIMIT:
                self.logs.append(f'{time.strftime("%H:%M:%S")}  {message}')

    def snapshot(self, since=0):
        with _lock:
            logs = self.logs[since:]
            total = len(self.logs)
        return {
            'id': self.id,
            'kind': self.kind,
            'title': self.title,
            'status': self.status,
            'progress': self.progress,
            'elapsed': round(time.time() - self.started),
            'logs': logs,
            'nextSince': total,
            'result': self.result,
            'wait': self.wait,
            'stage': self.stage,
            'stagePercent': self.stage_percent,
            'stageDone': self.stage_done,
            'stageTotal': self.stage_total,
            'options': self.options,
        }


_TQDM = re.compile(r'(\d{1,3})%\s*\|')
_TQDM_COUNT = re.compile(r'(\d+)/(\d+)')
_RATE_WAIT = re.compile(r'RATE_WAIT (\d+) (\d+)')


def _kill_proc(proc):
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True)
        else:
            proc.kill()
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


# 抓取子进程的 PID 落盘：后端重载/重启会丢掉内存里的任务对象，
# 靠这个文件在启动时清理遗留进程，保证全局只有一个抓取进程。
FETCH_PID_FILE = ROOT / 'fetch_data' / 'fetch.pid'


def _pid_is_fetch(pid):
    """确认 pid 仍是 fetch_kline.py 进程，避免 PID 被复用后误杀。"""
    if not pid or pid <= 0:
        return False
    try:
        if os.name == 'nt':
            out = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
                capture_output=True, text=True, timeout=20)
            return 'fetch_kline.py' in (out.stdout or '')
        os.kill(pid, 0)
        return True
    except Exception:  # noqa: BLE001
        return False


def _kill_pid(pid):
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)], capture_output=True)
        else:
            os.kill(pid, 9)
    except Exception:  # noqa: BLE001
        pass


def _cleanup_stray_fetch():
    """杀掉上次会话遗留的抓取进程（后端重启后任务已丢失，进程却还在跑）。"""
    try:
        pid = int(FETCH_PID_FILE.read_text(encoding='utf-8').strip())
    except Exception:  # noqa: BLE001
        return
    if _pid_is_fetch(pid):
        _kill_pid(pid)
    try:
        FETCH_PID_FILE.unlink()
    except OSError:
        pass


_cleanup_stray_fetch()

# 任务结束后把快照落库，页面刷新时若没有运行中的任务就展示上次执行情况。
CONSOLE_DB = Path(__file__).resolve().parent / 'console_jobs.db'
_SNAPSHOT_COLUMNS = 'kind TEXT PRIMARY KEY, payload TEXT'


def _save_last(job):
    job.wait = None
    payload = job.snapshot()
    payload['finished'] = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = sqlite3.connect(CONSOLE_DB)
        with conn:
            conn.execute(f'CREATE TABLE IF NOT EXISTS console_jobs ({_SNAPSHOT_COLUMNS})')
            conn.execute(
                'INSERT INTO console_jobs(kind, payload) VALUES(?, ?) '
                'ON CONFLICT(kind) DO UPDATE SET payload=excluded.payload',
                (job.kind, json.dumps(payload, ensure_ascii=False)))
        conn.close()
    except Exception:  # noqa: BLE001
        pass


def last_jobs():
    """每个类型最近一次执行完的任务快照（含完整日志）。"""
    try:
        conn = sqlite3.connect(CONSOLE_DB)
        conn.execute(f'CREATE TABLE IF NOT EXISTS console_jobs ({_SNAPSHOT_COLUMNS})')
        rows = conn.execute('SELECT kind, payload FROM console_jobs').fetchall()
        conn.close()
    except Exception:  # noqa: BLE001
        return {}
    result = {}
    for kind, payload in rows:
        try:
            result[kind] = json.loads(payload)
        except Exception:  # noqa: BLE001
            continue
    return result


def _board_args(options):
    """把页面勾选项转成抓取脚本的排除板块参数；北交所固定排除。"""
    boards = (options or {}).get('boards') or {}
    excluded = ['bj']
    if not boards.get('gem', True):
        excluded.append('gem')
    if not boards.get('star', True):
        excluded.append('star')
    return excluded


def _run_fetch(job):
    python = shutil.which('python') or sys.executable
    script = ROOT / 'fetch_data' / 'fetch_kline.py'
    excluded = _board_args(job.options)
    scope = '、'.join(name for name, key in (('主板', None), ('创业板', 'gem'), ('科创板', 'star'))
                     if key is None or key not in excluded)
    job.log(f'启动个股日线抓取：{script.name}（范围：{scope}）')
    # 子进程强制 UTF-8 输出，避免 Windows 控制台 GBK 造成日志乱码。
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    try:
        proc = subprocess.Popen(
            [python, '-u', str(script), '--defer-db', '--exclude-boards', *excluded],
            cwd=str(ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
        )
        job.proc = proc
        try:
            FETCH_PID_FILE.write_text(str(proc.pid), encoding='utf-8')
        except OSError:
            pass
        for chunk in proc.stdout:
            for line in chunk.replace('\r', '\n').split('\n'):
                line = line.strip()
                if not line:
                    continue
                percent = _TQDM.search(line)
                if percent:
                    raw = min(100, int(percent.group(1)))
                    # 下载占前 60%，批量入库占后 40%，两段共用一条总进度条。
                    phase = '入库' if '入库' in line else '下载'
                    job.stage = phase
                    job.stage_percent = raw
                    value = int(60 + raw * 0.4) if phase == '入库' else int(raw * 0.6)
                    job.progress = max(job.progress, value)
                    counts = _TQDM_COUNT.search(line)
                    if counts:
                        job.stage_done = int(counts.group(1))
                        job.stage_total = int(counts.group(2))
                    # 进度不再逐行写日志：前端用控制台底部的一行进度条展示。
                    continue
                wait = _RATE_WAIT.search(line)
                if wait:
                    left, total = int(wait.group(1)), int(wait.group(2))
                    job.wait = {'left': left, 'total': total} if total else None
                    if not total:
                        job.log('额度已恢复，继续下载')
                    continue
                if '频率超限' in line:
                    # Tushare 每条限流提示都在这里吞掉，前端不再刷屏；限流状态走 wait 字段渲染。
                    job.rate_limit_hits += 1
                    continue
                job.log(line)
        code = proc.wait()
        job.wait = None
        if job.cancelled:
            job.status = 'cancelled'
            job.log('抓取已取消（已下载的股票已保存，未下载的不再继续）')
        else:
            job.progress = 100
            job.status = 'done' if code == 0 else 'error'
            job.log('抓取完成' if code == 0 else f'抓取结束，退出码 {code}')
    except Exception as exc:  # noqa: BLE001
        job.status = 'error'
        job.wait = None
        job.log(f'抓取失败：{exc}')
    finally:
        job.proc = None
        try:
            FETCH_PID_FILE.unlink()
        except OSError:
            pass
        if job.status == 'running':
            job.status = 'cancelled' if job.cancelled else 'error'
        _save_last(job)


class _Cancelled(Exception):
    pass


def _picked_text(row):
    """控制台展示「代码 名称」，名称取不到时退回代码。"""
    from stock_meta import describe
    code = str(row['code'])
    name = describe(code)['name']
    return f'{code} {name}' if name and name != code else code


def _run_b1(job):
    from b1_selector import picks_for

    def progress(percent, message):
        if job.cancelled:
            raise _Cancelled()
        job.progress = max(0, min(100, int(percent)))
        if message:
            job.log(message)

    job.log('开始 B1 选股')
    excluded = [name for name in _board_args(job.options) if name != 'bj']
    j_threshold = (job.options or {}).get('jThreshold', 15)
    date = (job.options or {}).get('date') or None
    try:
        day, rows, _ = picks_for(date, True, progress=progress,
                                 exclude_boards=excluded, j_threshold=j_threshold)
        job.progress = 100
        job.status = 'done'
        job.result = {'date': day, 'count': len(rows)}
        job.log('============= 选股结果 =============')
        job.log(f'交易日：{day}')
        job.log(f'符合条件股票数：{len(rows)}')
        job.log(','.join(_picked_text(row) for row in rows) if rows else '（无）')
    except _Cancelled:
        job.status = 'cancelled'
        job.log('选股已取消')
    except Exception as exc:  # noqa: BLE001
        job.status = 'error'
        job.log(f'选股失败：{exc}')
    finally:
        _save_last(job)


def _find_running(kind):
    for job in _jobs.values():
        if job.kind == kind and job.status == 'running':
            return job
    return None


def start(kind, options=None):
    """kind: fetch | b1；同类型任务运行中则复用。options 为页面传入的筛选条件。"""
    running = _find_running(kind)
    if running:
        return running
    if kind == 'fetch':
        # 确保上一个抓取进程（可能是后端重载后遗留的孤儿）已经结束。
        _cleanup_stray_fetch()
    title = '拉取个股日线' if kind == 'fetch' else 'B1 选股'
    job = Job(kind, title, options)
    job.log(f'{title}任务已创建')
    with _lock:
        _jobs[job.id] = job
    target = _run_fetch if kind == 'fetch' else _run_b1
    threading.Thread(target=target, args=(job,), daemon=True).start()
    return job


def get(job_id, since=0):
    job = _jobs.get(job_id)
    return job.snapshot(since) if job else None


def active():
    """返回仍在运行的任务，供页面刷新后继续显示控制台。"""
    running = [job for job in _jobs.values() if job.status == 'running']
    if not running:
        return None
    return max(running, key=lambda item: item.started).snapshot()


def active_all():
    """返回所有仍在运行的任务，供页面刷新后分别恢复两个控制台。"""
    running = [job for job in _jobs.values() if job.status == 'running']
    return [job.snapshot() for job in sorted(running, key=lambda item: item.started)]


def cancel(job_id):
    """取消运行中的任务；拉取任务会杀掉子进程，已下载的股票保留。"""
    job = _jobs.get(job_id)
    if not job or job.status != 'running':
        return None
    job.cancelled = True
    job.log('收到取消请求，正在停止任务…')
    _kill_proc(job.proc)
    return job.snapshot()
