"""Default fetch end date following the 15:00 rule.

Before 15:00 local time, fetch scripts should target the previous trading day;
from 15:00 on, they target today. The date is always adjusted to a real trading
day (weekends and holidays fall back to the nearest open day) using the Tushare
trade calendar, with a weekday-only fallback when the calendar is unreachable.
"""
import datetime as dt
from zoneinfo import ZoneInfo

CUTOFF_HOUR = 15
_LOOKBACK_DAYS = 21
MARKET_TZ = ZoneInfo('Asia/Shanghai')


def latest_trading_day(target: dt.date) -> str:
    """Nearest SSE trading day on or before ``target`` as YYYYMMDD."""
    fmt = target.strftime('%Y%m%d')
    start = (target - dt.timedelta(days=_LOOKBACK_DAYS)).strftime('%Y%m%d')
    try:
        try:
            from .tushare_client import create_client
        except ImportError:
            from tushare_client import create_client
        frame = create_client().query('trade_cal', exchange='SSE', start_date=start, end_date=fmt)
        days = sorted(str(day) for day, opened in zip(frame['cal_date'], frame['is_open'])
                      if str(opened) == '1' and str(day) <= fmt)
        if days:
            return days[-1]
    except Exception:
        pass
    while target.weekday() >= 5:
        target -= dt.timedelta(days=1)
    return target.strftime('%Y%m%d')


def default_end_date(now: dt.datetime | None = None) -> str:
    """YYYYMMDD end date: before 15:00 Beijing time -> previous trading day, after -> today."""
    now = now or dt.datetime.now(MARKET_TZ)
    target = now.date() if now.hour >= CUTOFF_HOUR else now.date() - dt.timedelta(days=1)
    return latest_trading_day(target)
