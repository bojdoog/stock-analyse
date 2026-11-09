import base64
import csv
import json
from flask import Blueprint, current_app, jsonify, request
from market_store import PROJECT, connect, file_content
from research_storage import archive_key
from services.sector_activity import from_bytes

sector_activity_bp = Blueprint('sector_activity', __name__, url_prefix='/api/sector-activity')
MEMBERS_DIR = PROJECT / 'back_test_data' / 'ths_member'


def load():
    def source(relative):
        path = PROJECT / 'back_test_data' / relative
        _, key = archive_key(path)
        content = file_content(key, current_app.config['DATABASE_PATH'])
        if content is not None:
            return base64.b64decode(json.loads(content)['base64'])
        return path.read_bytes()
    return from_bytes(source('ths_daily/all_industries.csv'), source('metadata/industry_universe.json'),
                      source('ths_index/research_industries.csv'))


@sector_activity_bp.get('')
def sectors():
    try:
        items = load()
        day = request.args.get('date')
        dates = [p['date'] for p in next(iter(items.values()))['series']]
        if day and day not in dates:
            return jsonify(code=400, message='请选择数据范围内的交易日'), 400
        day = day or dates[-1]
        i = dates.index(day)
        data = [{**{k: v for k, v in item.items() if k != 'series'}, **item['series'][i]} for item in items.values()]
        data.sort(key=lambda x: x['change5'] if x['change5'] is not None else float('-inf'), reverse=True)
        return jsonify(code=0, data=data, dates=dates, date=day)
    except (ValueError, OSError, KeyError) as exc:
        current_app.logger.warning('Sector activity unavailable: %s', type(exc).__name__)
        return jsonify(code=503, message='板块数据不完整或暂不可用，请更新行业数据后重试'), 503


@sector_activity_bp.get('/<code>')
def sector(code):
    try:
        item = load().get(code)
        if item is None:
            return jsonify(code=404, message='板块不存在'), 404
        return jsonify(code=0, data=item)
    except (ValueError, OSError, KeyError):
        return jsonify(code=503, message='板块数据不完整或暂不可用'), 503


def members(code):
    """读取同花顺板块成分股对照表；单板块文件缺失时回退到全量文件。"""
    path = MEMBERS_DIR / f'{code}.csv'
    if not path.exists():
        path = MEMBERS_DIR / 'all_industries.csv'
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return [row for row in csv.DictReader(handle)
                if row.get('ts_code') == code and (row.get('is_new') or 'Y') == 'Y']


def ema(values, span):
    step = 2 / (span + 1)
    result, previous = [], values[0]
    for index, value in enumerate(values):
        previous = value if index == 0 else previous + step * (value - previous)
        result.append(previous)
    return result


def moving_average(values, window):
    return [sum(values[index - window + 1:index + 1]) / window if index >= window - 1 else None
            for index in range(len(values))]


def zx_above(closes):
    """知行短期趋势线（收盘 EMA10 再 EMA10）是否高于知行多空线（MA14/28/57/114 均值）。"""
    if len(closes) < 114:
        return None
    short = ema(ema(closes, 10), 10)[-1]
    longs = [moving_average(closes, window)[-1] for window in (14, 28, 57, 114)]
    return short > sum(longs) / len(longs)


@sector_activity_bp.get('/<code>/stocks')
def sector_stocks(code):
    """板块成分股截至指定交易日的行情，用于弹窗展示。"""
    try:
        item = load().get(code)
        if item is None:
            return jsonify(code=404, message='板块不存在'), 404
        day = request.args.get('date') or item['series'][-1]['date']
        rows = members(code)
        names = {row['con_code'].split('.')[0]: row['con_name'] for row in rows if row.get('con_code')}
        if not names:
            return jsonify(code=0, data=[], date=day, total=0)
        with connect(current_app.config['DATABASE_PATH']) as db:
            # 取 200 个交易日，足够 MA114 与 EMA 热身。
            dates = [row['date'] for row in db.execute(
                "SELECT DISTINCT date FROM daily_bars WHERE category='stock' AND date<=?"
                ' ORDER BY date DESC LIMIT 200', (day,))]
            if not dates:
                return jsonify(code=0, data=[], date=day, total=0)
            marks = ','.join('?' for _ in dates)
            codes = list(names)
            quotes = {}
            for start in range(0, len(codes), 300):
                chunk = codes[start:start + 300]
                sql = ("SELECT code, date, close, volume FROM daily_bars WHERE category='stock'"
                       f' AND date IN ({marks}) AND code IN ({",".join("?" for _ in chunk)})')
                for bar in db.execute(sql, list(dates) + chunk):
                    quotes.setdefault(bar['code'], {})[bar['date']] = (float(bar['close']), bar['volume'])
            # 换手率取指标表中不晚于该交易日的最近一期。
            turnovers = {}
            basic = db.execute('SELECT MAX(date) AS day FROM stock_daily_basic WHERE date<=?', (day,)).fetchone()
            if basic and basic['day']:
                for start in range(0, len(codes), 300):
                    chunk = codes[start:start + 300]
                    sql = ('SELECT code, turnover_rate FROM stock_daily_basic WHERE date=?'
                           f' AND code IN ({",".join("?" for _ in chunk)})')
                    for row in db.execute(sql, [basic['day']] + chunk):
                        turnovers[row['code']] = row['turnover_rate']
        data = []
        for code_, name in names.items():
            series = quotes.get(code_)
            if not series:
                continue
            # 按日期升序，涨幅与指标都基于个股自身可用交易日，停牌日不计入间隔。
            ordered = [series[d] for d in reversed(dates) if d in series]
            closes = [close for close, _ in ordered]
            change = round((closes[-1] / closes[-2] - 1) * 100, 2) if len(closes) > 1 and closes[-2] else None
            change5 = round((closes[-1] / closes[-6] - 1) * 100, 2) if len(closes) > 5 and closes[-6] else None
            volume = ordered[-1][1]
            data.append({'code': code_, 'name': name, 'change': change, 'change5': change5,
                         'volume': float(volume) if volume is not None else None,
                         'turnover': turnovers.get(code_), 'cross': zx_above(closes)})
        data.sort(key=lambda row: row['change'] if row['change'] is not None else float('-inf'), reverse=True)
        return jsonify(code=0, data=data, date=dates[0], total=len(data))
    except (ValueError, OSError, KeyError):
        return jsonify(code=503, message='板块成分股数据暂不可用'), 503
