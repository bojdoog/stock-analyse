#!/usr/bin/env python3
"""抓取个股每日指标（市值、股本、PE、PB、换手率、量比）写入 stock_daily_basic 表。

以交易日为粒度调用 Tushare daily_basic，一次返回全市场个股，已入库的日期自动跳过。

用法：
  python fetch_data/fetch_daily_basic.py
  python fetch_data/fetch_daily_basic.py --start 20250101 --end 20261110
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import tushare as ts
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask_backend'))
from market_store import connect
from stock_basic_daily import TABLE, existing_dates, save_rows

try:
    from .trading_date import default_end_date
except ImportError:
    from trading_date import default_end_date

LOG_FILE = Path(__file__).resolve().parent / 'fetch.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8'),
    ],
)
logger = logging.getLogger('fetch_daily_basic')

FIELDS = 'ts_code,trade_date,close,turnover_rate,pe_ttm,pb,total_mv,circ_mv,float_share,volume_ratio'
TS_TOKEN = 'eb0e5fcfd014dfb595b4ca773f42d29570a3fb06edcca84fe19830db'
RETRIES = 3


def iso_date(value):
    text = str(value)
    return f'{text[:4]}-{text[4:6]}-{text[6:8]}'


def trade_days(pro, start, end):
    """交易日历取开市日；接口不可用时退化为工作日。"""
    try:
        frame = pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open='1')
        return sorted(frame['cal_date'].astype(str))
    except Exception as exc:  # noqa: BLE001 - 交易日历权限或网络异常都降级处理
        logger.warning('交易日历不可用（%s），按工作日抓取', exc)
        current = dt.date.fromisoformat(iso_date(start))
        last = dt.date.fromisoformat(iso_date(end))
        days = []
        while current <= last:
            if current.weekday() < 5:
                days.append(current.strftime('%Y%m%d'))
            current += dt.timedelta(days=1)
        return days


def fetch_day(pro, day):
    for attempt in range(RETRIES):
        try:
            return pro.daily_basic(trade_date=day, fields=FIELDS)
        except Exception as exc:  # noqa: BLE001 - 限流与网络错误统一重试
            message = str(exc)
            limit = any(word in message for word in ('频率', '频繁', '429', 'too many'))
            wait = 60 if limit else 15 * (attempt + 1)
            logger.warning('%s 抓取失败（%s），%s 秒后重试', day, message[:80], wait)
            time.sleep(wait)
    raise RuntimeError(f'{day} 连续 {RETRIES} 次抓取失败')


def stock_catalog(pro, db):
    """代码 → (名称, 地区, 行业)；优先 Tushare stock_basic，失败时沿用库内已有名称。"""
    try:
        frame = pro.stock_basic(exchange='', list_status='L',
                                fields='ts_code,symbol,name,area,industry')
        return {str(code)[:6]: (name, area or None, industry or None)
                for code, name, area, industry in frame[
                    ['ts_code', 'name', 'area', 'industry']].itertuples(index=False, name=None)}
    except Exception as exc:  # noqa: BLE001 - 基础信息失败不影响行情指标
        logger.warning('stock_basic 不可用（%s），沿用库内已有名称', exc)
        return {row['code']: (row['name'], row['area'], row['industry']) for row in db.execute(
            f'SELECT code, MAX(name) AS name, MAX(area) AS area, MAX(industry) AS industry'
            f' FROM {TABLE} GROUP BY code')}


def _num(value):
    return None if value is None or pd.isna(value) else float(value)


def to_rows(frame, catalog):
    """转换成 stock_daily_basic.COLUMNS 顺序的元组，并补上名称/地区/行业；NaN 置空。"""
    if frame is None or frame.empty:
        return []
    rows = []
    for item in frame.itertuples(index=False):
        values = dict(zip(FIELDS.split(','), item))
        code = str(values['ts_code'])[:6]
        name, area, industry = catalog.get(code, (None, None, None))
        text = str(values['trade_date'])
        rows.append((
            f'{text[:4]}-{text[4:6]}-{text[6:8]}', code,
            _num(values['close']), _num(values['turnover_rate']), _num(values['pe_ttm']),
            _num(values['pb']), _num(values['total_mv']), _num(values['circ_mv']),
            _num(values['float_share']), _num(values['volume_ratio']),
            name, area, industry,
        ))
    return rows


def main():
    parser = argparse.ArgumentParser(description='抓取个股每日指标（daily_basic）入库')
    parser.add_argument('--start', default='20240101', help='起始日期 YYYYMMDD 或 today')
    parser.add_argument('--end', default='today', help='结束日期 YYYYMMDD 或 today')
    args = parser.parse_args()

    os.environ['NO_PROXY'] = 'api.waditu.com,.waditu.com,waditu.com'
    os.environ['no_proxy'] = os.environ['NO_PROXY']
    ts.set_token(TS_TOKEN)
    pro = ts.pro_api()

    start = dt.date.today().strftime('%Y%m%d') if str(args.start).lower() == 'today' else str(args.start)
    end = default_end_date() if str(args.end).lower() == 'today' else str(args.end)
    days = trade_days(pro, start, end)
    if not days:
        logger.warning('区间 %s → %s 没有交易日', start, end)
        return

    total = 0
    with connect() as db:
        done = existing_dates(db, iso_date(days[0]), iso_date(days[-1]))
        pending = [day for day in days if iso_date(day) not in done]
        logger.info('区间 %s → %s 共 %s 个交易日，已入库 %s 天，待抓取 %s 天',
                    days[0], days[-1], len(days), len(done), len(pending))
        catalog = stock_catalog(pro, db) if pending else {}
        for day in tqdm(pending, desc='每日指标', unit='天'):
            rows = to_rows(fetch_day(pro, day), catalog)
            total += save_rows(db, rows)
    logger.info('抓取完成，共写入 %s 行', total)


if __name__ == '__main__':
    main()
