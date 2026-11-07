"""Download reproducible AMV research inputs through the shared Tushare relay SDK (read-only).

Provider and credentials are selected through tushare_config.ini.
No credential is stored in the output. Successful requests are cached for resume.
"""
from __future__ import annotations

import csv
import argparse
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import time

import requests

try:
    from .permission_errors import is_permission_denied, SKIP_EXIT_CODE
except ImportError:
    from permission_errors import is_permission_denied, SKIP_EXIT_CODE

try:
    from .trading_date import default_end_date
except ImportError:
    from trading_date import default_end_date

DENIED_TOOLS = set()


class InterfacePermissionDenied(RuntimeError):
    pass

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "back_test_data"
START = '20240910'
END = default_end_date()
MANIFEST: list[dict] = []
FAILURES: list[dict] = []
try:
    from .tushare_client import ENDPOINT, RelayClient, get_token, get_settings
except ImportError:
    from tushare_client import ENDPOINT, RelayClient, get_token, get_settings
SESSION = requests.Session()

THS_DAILY_FIELDS = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'pre_close',
                    'pct_change', 'vol', 'avg_price', 'turnover_rate', 'float_mv', 'total_mv']


def with_ths_amount(rows):
    """Derive turnover in yuan from volume (hands) and average price (yuan/share).

    Missing/invalid inputs remain null rather than masquerading as zero turnover.
    Keep the upstream fields and response separate from the locally derived amount.
    """
    result = []
    for row in rows:
        amount = None
        try:
            volume = Decimal(str(row.get('vol')))
            price = Decimal(str(row.get('avg_price')))
            if volume.is_finite() and price.is_finite() and volume >= 0 and price > 0:
                value = volume * Decimal(100) * price
                if value.is_finite() and value <= Decimal('1e308'):
                    amount = float(value)
        except (InvalidOperation, ValueError, TypeError):
            pass
        result.append({**row, 'avg_price': row.get('avg_price'), 'amount': amount})
    return result


def write_bytes_retry(path: Path, content: bytes, attempts: int = 8, delay: float = 0.5):
    """Write bytes, retrying transient locks from indexers/antivirus.

    A workspace file can be memory-mapped by another process for a short
    window, which makes an in-place rewrite fail with EINVAL. Fall back to
    writing a sibling temporary file and renaming it into place.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.writing')
    last = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay * attempt)
        try:
            path.write_bytes(content)
            temp.unlink(missing_ok=True)
            return
        except OSError as exc:
            last = exc
        try:
            temp.write_bytes(content)
            os.replace(temp, path)
            return
        except OSError as exc:
            last = exc
    temp.unlink(missing_ok=True)
    raise last


def write_json(path: Path, obj):
    write_bytes_retry(path, json.dumps(obj, ensure_ascii=False, indent=2).encode('utf-8'))
    archive_output(path)


def write_csv(path: Path, rows: list[dict]):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    buffer = io.StringIO()
    if fields:
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    write_bytes_retry(path, buffer.getvalue().encode('utf-8-sig'))
    archive_output(path)


def archive_output(path):
    import sys
    sys.path.insert(0, str(PROJECT / 'flask_backend'))
    from research_storage import archive_file
    archive_file(path)


def read_csv(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def redact(message):
    return str(message).replace(get_token(), '[REDACTED]')


def rpc(method: str, params: dict):
    tool = params.get("name", method)
    if tool in DENIED_TOOLS:
        raise InterfacePermissionDenied(tool)
    for attempt in range(4):
        try:
            if method == 'tools/list':
                settings = get_settings()
                return {'tools': [], 'transport': 'SDK', 'provider': settings['provider'], 'endpoint': settings['url']}
            frame = RelayClient(session=SESSION).query(tool, **params.get('arguments', {}))
            result = {'content': [{'type': 'text', 'text': frame.to_json(orient='records', force_ascii=False)}]}
            time.sleep(0.12)
            return result
        except Exception as exc:
            error = redact(exc)
            if is_permission_denied(error):
                DENIED_TOOLS.add(tool)
                print(f"[SKIP] {tool}: no API permission; skipping this dataset.", flush=True)
                raise InterfacePermissionDenied(tool) from None
            if attempt == 3:
                raise RuntimeError(error) from None
            print(f'retry {method} {attempt + 1}: {error[:180]}', flush=True)
            time.sleep(min(2 ** (attempt + 1), 8))


def query(tool: str, arguments: dict, key: str):
    if tool in DENIED_TOOLS:
        raise InterfacePermissionDenied(tool)
    cache = ROOT / 'raw' / tool / (key + '.json')
    signature = {'tool': tool, 'arguments': arguments}
    import sys
    sys.path.insert(0, str(PROJECT / 'flask_backend'))
    from research_storage import read_file
    cached_content = read_file(cache)
    if cached_content is not None:
        saved = json.loads(cached_content)
        # Today's observations may still change; do not reuse an intraday snapshot.
        current_day = dt.date.today().strftime('%Y%m%d')
        request_end = arguments.get('end_date', arguments.get('trade_date'))
        if saved.get('request') == signature and request_end is not None and str(request_end) < current_day:
            cache.parent.mkdir(parents=True, exist_ok=True)
            rows = saved['rows']
            if tool == 'ths_daily':
                rows = with_ths_amount(rows)
                saved['rows'] = rows
                saved['derived_amount'] = {'formula': 'vol * 100 * avg_price', 'unit': 'CNY'}
            write_json(cache, saved)
            write_csv(cache.with_suffix('.csv'), rows)
            MANIFEST.append({'tool': tool, 'key': key, 'rows': len(rows), 'cached': True})
            return rows
    result = rpc('tools/call', {'name': tool, 'arguments': arguments})
    rows = []
    for block in result.get('content', []):
        if block.get('type') != 'text':
            continue
        value = json.loads(block['text'])
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise RuntimeError(f'{tool}: unexpected data response')
        rows.extend(value)
    if tool == 'ths_daily':
        rows = with_ths_amount(rows)
    payload = {'request': signature, 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(),
               'result': result, 'rows': rows}
    if tool == 'ths_daily':
        payload['derived_amount'] = {'formula': 'vol * 100 * avg_price', 'unit': 'CNY'}
    write_json(cache, payload)
    write_csv(cache.with_suffix('.csv'), rows)
    MANIFEST.append({'tool': tool, 'key': key, 'rows': len(rows), 'cached': False})
    return rows


def months():
    cursor = dt.datetime.strptime(START, '%Y%m%d').date()
    stop = dt.datetime.strptime(END, '%Y%m%d').date()
    while cursor <= stop:
        next_month = (cursor.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        end = min(next_month - dt.timedelta(days=1), stop)
        yield cursor.strftime('%Y%m%d'), end.strftime('%Y%m%d')
        cursor = next_month


def monthly(tool: str, cap: int, expected: set[str]):
    rows = []
    for start, end in months():
        batch = query(tool, {'start_date': start, 'end_date': end}, start + '_' + end)
        if len(batch) >= cap:
            # Never accept a potentially truncated batch: retry by individual date.
            batch = []
            cursor = dt.datetime.strptime(start, '%Y%m%d').date()
            stop = dt.datetime.strptime(end, '%Y%m%d').date()
            while cursor <= stop:
                day = cursor.strftime('%Y%m%d')
                part = query(tool, {'trade_date': day}, 'day_' + day)
                if len(part) >= cap:
                    raise RuntimeError(f'{tool} {day}: possible row limit truncation')
                batch.extend(part)
                cursor += dt.timedelta(days=1)
        rows.extend(batch)
    # Query missing dates individually to distinguish range-query gaps from source gaps.
    for day in sorted(expected - {str(r.get('trade_date', '')) for r in rows}):
        part = query(tool, {'trade_date': day}, 'missing_' + day)
        if len(part) >= cap:
            raise RuntimeError(f'{tool} {day}: possible row limit truncation')
        rows.extend(part)
    rows.sort(key=lambda r: (str(r.get('trade_date', '')), str(r.get('ts_code', ''))))
    write_csv(ROOT / tool / f'{START}_{END}.csv', rows)
    print(f'{tool}: {len(rows)} rows', flush=True)
    return rows


def audit_table(name, rows, expected, date_field='trade_date', key_fields=None):
    dates = {str(r.get(date_field, '')).replace('-', '') for r in rows}
    by_day = {}
    for row in rows:
        day = str(row.get(date_field, '')).replace('-', '')
        by_day[day] = by_day.get(day, 0) + 1
    fields = list(dict.fromkeys(k for row in rows for k in row))
    result = {'rows': len(rows), 'dates': len(dates), 'min_date': min(dates, default=None),
              'max_date': max(dates, default=None), 'missing_dates': sorted(expected - dates),
              'unexpected_dates': sorted(dates - expected), 'rows_per_date': by_day,
              'null_counts': {k: sum(r.get(k) is None or r.get(k) == '' for r in rows) for k in fields}}
    if key_fields:
        keys = [tuple(str(r.get(k)) for k in key_fields) for r in rows]
        result['duplicate_keys'] = len(keys) - len(set(keys))
    return result


def main(argv=None):
    global START, END
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='20240910', help='Start date, YYYYMMDD')
    parser.add_argument('--end', default=default_end_date(), help='End date, YYYYMMDD (default: 15:00 rule)')
    args = parser.parse_args(argv)
    try:
        start = dt.datetime.strptime(args.start, '%Y%m%d').date()
        end = dt.datetime.strptime(args.end, '%Y%m%d').date()
    except ValueError:
        parser.error('Dates must be valid YYYYMMDD dates')
    if start > end:
        parser.error('--start must not be after --end')
    START, END = start.strftime('%Y%m%d'), end.strftime('%Y%m%d')
    MANIFEST.clear()
    FAILURES.clear()
    DENIED_TOOLS.clear()
    print(f'AMV research download: {START} to {END}', flush=True)
    metadata = ROOT / 'metadata'
    metadata.mkdir(parents=True, exist_ok=True)
    catalog = rpc('tools/list', {})
    write_json(metadata / 'relay_config.json', catalog)
    settings = get_settings()
    print(f"Tushare SDK: {settings['provider']} | {settings['url']}", flush=True)

    import sys
    sys.path.insert(0, str(PROJECT / 'flask_backend'))
    from market_store import file_content, list_files
    (ROOT / 'amv').mkdir(exist_ok=True)
    source = ROOT / 'amv/source_original.csv'
    write_bytes_retry(source, file_content('core_index/0AMV-2013-2026.csv'))
    amv = [r for r in read_csv(source) if START <= r['date'].replace('-', '') <= END]
    write_csv(ROOT / 'amv' / f'{START}_{END}.csv', amv)

    local_dir = ROOT / 'local_industry_reference'
    local_dir.mkdir(exist_ok=True)
    local_rows = []
    for filename in list_files('moneyflow_ind_ths'):
        file = local_dir / filename
        if START <= file.stem <= END:
            write_bytes_retry(file, file_content(f'moneyflow_ind_ths/{filename}'))
            local_rows.extend(read_csv(file))

    calendars = {}
    for exchange in ('SSE', 'SZSE'):
        rows = query('trade_cal', {'exchange': exchange, 'start_date': START, 'end_date': END}, exchange)
        rows.sort(key=lambda r: str(r['cal_date']))
        write_csv(ROOT / 'trade_cal' / f'{exchange}_{START}_{END}.csv', rows)
        calendars[exchange] = {str(r['cal_date']) for r in rows if str(r['is_open']) == '1'}
    expected = calendars['SSE'] | calendars['SZSE']

    try:
        index_rows = query('ths_index', {'fields': 'ts_code,name,count,exchange,list_date,type', 'limit': 20000}, 'relay_catalog')
        if len(index_rows) >= 20000:
            raise RuntimeError('ths_index catalog reached response limit; refusing an incomplete snapshot')
        index_rows = [row for row in index_rows if row.get('exchange') == 'A' and row.get('type') == 'I']
        write_csv(ROOT / 'ths_index/industry_snapshot.csv', index_rows)
    except InterfacePermissionDenied:
        index_rows = []

    datasets = {}
    for tool, cap in [('moneyflow_ind_ths', 5000), ('daily_info', 4000),
                      ('sz_daily_info', 2000), ('moneyflow_mkt_dc', 3000)]:
        try:
            datasets[tool] = monthly(tool, cap, expected)
        except InterfacePermissionDenied:
            pass
        except Exception as exc:
            FAILURES.append({'tool': tool, 'error': redact(exc)})
            print(f'FAILED {tool}: {redact(exc)[:250]}', flush=True)

    # The catalog contains multiple overlapping classification hierarchies. Use the
    # historical flow universe (90 industries), not every catalog entry.
    codes = sorted({r['ts_code'] for r in datasets.get('moneyflow_ind_ths', []) + local_rows
                    if r.get('ts_code')})
    previous_universe = metadata / 'industry_universe.json'
    if previous_universe.exists():
        codes = sorted(set(codes) | set(json.loads(previous_universe.read_text(encoding='utf-8'))['codes']))
    if codes:
        write_json(previous_universe, {'codes': codes, 'source': 'historical flow, local reference and existing universe'})
    if index_rows:
        write_csv(ROOT / 'ths_index/research_industries.csv', [r for r in index_rows if r.get('ts_code') in codes])
    # Preserve any already-downloaded alternative classification data separately.
    for dataset in ('ths_daily', 'ths_member'):
        folder = ROOT / dataset
        if folder.exists():
            for file in folder.glob('*.TI.csv'):
                if file.stem not in codes:
                    destination = ROOT / 'supplemental_classifications' / dataset / file.name
                    if ROOT.resolve() not in file.resolve().parents or ROOT.resolve() not in destination.resolve().parents:
                        raise RuntimeError('Invalid archive path')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    file.replace(destination)
    all_daily = []
    all_members = []
    for number, code in enumerate(codes, 1):
        try:
            rows = query('ths_daily', {'ts_code': code, 'start_date': START, 'end_date': END,
                                      'fields': THS_DAILY_FIELDS}, code)
            if len(rows) >= 3000:
                raise RuntimeError(f'{code}: possible row limit truncation')
            rows.sort(key=lambda r: str(r.get('trade_date', '')))
            write_csv(ROOT / 'ths_daily' / (code + '.csv'), rows)
            missing_amount = sum(r.get('amount') is None for r in rows)
            if missing_amount:
                print(f'[WARN] {code}: {missing_amount} rows lack valid vol/avg_price; amount left empty.', flush=True)
            all_daily.extend(rows)
        except InterfacePermissionDenied:
            pass
        except Exception as exc:
            FAILURES.append({'tool': 'ths_daily', 'code': code, 'error': redact(exc)})
        try:
            members = []
            offset = 0
            while True:
                part = query('ths_member', {'ts_code': code, 'offset': offset,
                    'fields': ['ts_code', 'con_code', 'con_name', 'is_new', 'weight', 'in_date', 'out_date']},
                    code + '_' + str(offset))
                if offset and part and part == members[:len(part)]:
                    raise RuntimeError('pagination repeated the first page')
                members.extend(part)
                if len(part) < 5000:
                    break
                offset += len(part)
            write_csv(ROOT / 'ths_member' / (code + '.csv'), members)
            all_members.extend(members)
        except InterfacePermissionDenied:
            pass
        except Exception as exc:
            FAILURES.append({'tool': 'ths_member', 'code': code, 'error': redact(exc)})
        if number % 10 == 0 or number == len(codes):
            print(f'Industry progress {number}/{len(codes)}; prices={len(all_daily)} members={len(all_members)} failures={len(FAILURES)}', flush=True)

    if all_daily and 'ths_daily' not in DENIED_TOOLS:
        write_csv(ROOT / 'ths_daily/all_industries.csv', all_daily)
    if all_members and 'ths_member' not in DENIED_TOOLS:
        write_csv(ROOT / 'ths_member/all_industries.csv', all_members)
    datasets['ths_daily'] = all_daily
    quality = {'start': START, 'end': END, 'expected_trading_days': len(expected),
               'ths_daily_amount': {'formula': 'vol * 100 * avg_price', 'unit': 'CNY', 'source': 'derived'},
               'calendar_disagreements': sorted(calendars['SSE'] ^ calendars['SZSE']),
               'datasets': {}, 'failures': FAILURES, 'skipped_interfaces': sorted(DENIED_TOOLS)}
    for name, rows in datasets.items():
        quality['datasets'][name] = audit_table(name, rows, expected,
            key_fields=['trade_date'] if name == 'moneyflow_mkt_dc' else ['trade_date', 'ts_code'])
    quality['datasets']['amv'] = audit_table('amv', amv, expected, 'date', ['date'])
    quality['datasets']['local_industry_reference'] = audit_table('local', local_rows, expected, 'date', ['date', 'ts_code'])
    quality['industry_prices'] = {}
    for code in codes:
        rows = [r for r in all_daily if r.get('ts_code') == code]
        result = audit_table(code, rows, expected, key_fields=['trade_date', 'ts_code'])
        result.pop('rows_per_date')
        quality['industry_prices'][code] = result
    flow = datasets.get('moneyflow_ind_ths', [])
    quality['all_zero_flow_dates'] = []
    for day in sorted({r['trade_date'] for r in flow}):
        rows = [r for r in flow if r['trade_date'] == day]
        fields = ['net_buy_amount', 'net_sell_amount', 'net_amount']
        if rows and all(r.get(k) is not None and float(r[k]) == 0 for r in rows for k in fields):
            quality['all_zero_flow_dates'].append(day)
    quality['member_snapshot'] = {'rows': len(all_members),
        'with_in_date': sum(bool(r.get('in_date')) for r in all_members),
        'with_out_date': sum(bool(r.get('out_date')) for r in all_members),
        'warning': 'Membership is a retrieval-time snapshot; date fields do not guarantee complete historical membership.'}
    write_json(ROOT / 'quality_report.json', quality)
    write_json(ROOT / 'download_manifest.json', {'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'start': START, 'end': END, 'requests': MANIFEST, 'failures': FAILURES, 'skipped_interfaces': sorted(DENIED_TOOLS),
        'amv_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest()})

    lines = ['# 活跃市值反推研究数据', '',
        '使用前请阅读 [字段与单位说明](DATA_DICTIONARY.md) 和 [数据质量检查](quality/README.md)。', '',
        f'研究区间：{START}—{END}。交易日历覆盖 {len(expected)} 个交易日。', '',
        '通过 Tushare Relay SDK 只读下载；token 不写入数据。原始返回保存在 raw，清单保存在 download_manifest.json。', '',
        '| 目录 | 内容 |', '|---|---|',
        '| amv | 原始 AMV 文件副本及研究区间 CSV |',
        '| ths_daily | 各行业量价、均价、成交额、换手率和市值；另有合并 CSV |',
        '| moneyflow_ind_ths | 未做 ETF 映射过滤的行业资金流 |',
        '| daily_info / sz_daily_info | 市场每日统计及深圳补充统计 |',
        '| moneyflow_mkt_dc | 东方财富大盘资金流 |',
        '| ths_index / ths_member | 行业目录和成分快照 |',
        '| trade_cal | 沪深交易日历 |',
        '| local_industry_reference | 现有 74 行业数据副本，用于核对 |',
        '| metadata | MCP 接口定义及行业代码全集 |', '',
        '## 使用注意', '',
        '- 空值、零值、日期缺口保留原样，不插值、不把缺失补零。详见 quality_report.json。',
        '- 行业及概念不能未经检查直接相加；交易所总计与分项存在重叠。',
        '- 行业目录含多套重叠分类；主要行情与成分使用资金流接口中的行业代码。supplemental_classifications 为另外下载的分类数据，仅供参考。',
        '- 成分是下载时快照，即使带纳入/剔除日期也需验证历史完整性；不能直接作为历史成分使用。',
        '- moneyflow_ind_ths 的 close 是板块指数，close_price 是领涨股价格，不能混用。',
        '- ths_daily 的流通市值已包含价格，不应再乘指数点位。',
        '- ths_daily 保存 avg_price；amount = vol（手）×100×avg_price，单位为元，属于本地推算字段。缺失或无效输入保留空值。',
        '- 尚未加入模型预热期；当前只提供约定研究区间。',
        '- 单次抽样成功不能保证全区间字段完整，字段空值比例见质量报告。', '',
        '## 下载结果', '']
    for name, result in quality['datasets'].items():
        lines.append(f'- {name}: {result["rows"]} 行，{result["dates"]} 个日期，缺 {len(result["missing_dates"])} 个交易日。')
    lines += ['', f'全零行业资金日：{quality["all_zero_flow_dates"]}', f'失败请求：{len(FAILURES)}', '',
              '重复运行 python fetch_data/download_amv_research.py 可复用成功请求缓存并重试失败部分。']
    write_bytes_retry(ROOT / 'README.md', ('\n'.join(lines) + '\n').encode('utf-8'))
    print(json.dumps({'complete': not FAILURES and not DENIED_TOOLS, 'skipped_interfaces': sorted(DENIED_TOOLS), 'industry_codes': len(codes), 'expected_days': len(expected),
          'datasets': {k: {'rows': v['rows'], 'missing_days': len(v['missing_dates'])} for k, v in quality['datasets'].items()},
          'zero_flow_days': quality['all_zero_flow_dates'], 'failures': FAILURES}, ensure_ascii=False), flush=True)
    return 1 if FAILURES else (SKIP_EXIT_CODE if DENIED_TOOLS else 0)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except InterfacePermissionDenied:
        raise SystemExit(SKIP_EXIT_CODE) from None
