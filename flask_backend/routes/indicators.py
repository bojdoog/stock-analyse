from flask import Blueprint, jsonify, request

from database import get_db
from services.data_service import DataService

indicators_bp = Blueprint('indicators', __name__, url_prefix='/api/indicators')


@indicators_bp.route('/<int:indicator_id>/intraday', methods=['GET'])
def indicator_intraday(indicator_id):
    from datetime import datetime
    day = request.args.get('date', '')
    try:
        if datetime.strptime(day, '%Y-%m-%d').strftime('%Y-%m-%d') != day:
            raise ValueError
    except ValueError:
        return jsonify(code=400, message='date 须为 YYYY-MM-DD 格式的有效日期'), 400
    db = get_db()
    indicator = db.execute('SELECT code,name FROM indicators WHERE id=?', (indicator_id,)).fetchone()
    if indicator is None:
        return jsonify(code=404, message='指标不存在'), 404
    rows = db.execute('''SELECT time,amv FROM indicator_intraday
        WHERE indicator_id=? AND date=? ORDER BY time''', (indicator_id, day)).fetchall()
    previous = db.execute('''SELECT date,close FROM indicator_daily
        WHERE indicator_id=? AND date<? ORDER BY date DESC LIMIT 1''', (indicator_id, day)).fetchone()
    neighbors = {}
    for key, comparison, order in [('previousDate', '<', 'DESC'), ('nextDate', '>', 'ASC')]:
        row = db.execute(f'''SELECT date FROM indicator_intraday
            WHERE indicator_id=? AND date{comparison}? ORDER BY date {order} LIMIT 1''',
            (indicator_id, day)).fetchone()
        neighbors[key] = row[0] if row else None
    return jsonify(code=0, message='success', data=[dict(row) for row in rows], meta={
        'date': day, 'code': indicator['code'], 'name': indicator['name'], 'count': len(rows),
        'previousClose': previous['close'] if previous else None,
        'previousCloseDate': previous['date'] if previous else None, **neighbors,
    })


@indicators_bp.route('/<int:indicator_id>/data', methods=['GET'])
def indicator_data(indicator_id):
    indicator = get_db().execute(
        'SELECT code FROM indicators WHERE id = ?', (indicator_id,),
    ).fetchone()
    if indicator is None:
        return jsonify(code=404, message='指标不存在'), 404
    coverage = get_db().execute('''SELECT COUNT(*) AS count,
        SUM(CASE WHEN open IS NOT NULL OR high IS NOT NULL OR low IS NOT NULL THEN 1 ELSE 0 END) AS ohlc
        FROM indicator_daily WHERE indicator_id=?''', (indicator_id,)).fetchone()
    if not coverage['count']:
        return jsonify(code=404, message='该指标尚未配置行情数据'), 404
    data = DataService().get_indicator_data(indicator_id, request.args.get('start_date'),
                                           request.args.get('end_date'), request.args.get('limit', type=int))
    close_only = not coverage['ohlc']
    return jsonify(code=0, message='success', data=data, meta={'close_only': close_only})


@indicators_bp.route('', methods=['GET'])
def list_indicators():
    """Return database-backed, filtered and paginated indicator definitions."""
    try:
        current = int(request.args.get('current', '1'))
        page_size = int(request.args.get('pageSize', '10'))
        if current < 1 or current > 2147483647 or not 1 <= page_size <= 100:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(code=400, success=False,
                       message='current 须为正整数，pageSize 须为 1 到 100 的整数'), 400

    conditions = []
    values = []
    for field in ('name', 'code'):
        value = request.args.get(field, '').strip()
        if value:
            # Treat %, _ and backslash literally in user-entered search text.
            value = value.replace('!', '!!').replace('%', '!%').replace('_', '!_')
            conditions.append(f"{field} LIKE ? ESCAPE '!'")
            values.append(f'%{value}%')
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    db = get_db()
    total = db.execute('SELECT COUNT(*) FROM indicators' + where, values).fetchone()[0]
    rows = db.execute(
        'SELECT * FROM indicators' + where +
        ' ORDER BY is_default DESC, id ASC LIMIT ? OFFSET ?',
        [*values, page_size, (current - 1) * page_size],
    ).fetchall()
    data = [{**dict(row), 'is_default': bool(row['is_default'])} for row in rows]
    return jsonify(code=0, message='success', success=True, data=data, total=total,
                   current=current, pageSize=page_size)
