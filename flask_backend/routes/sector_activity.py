import base64
import json
from flask import Blueprint, current_app, jsonify, request
from market_store import PROJECT, file_content
from research_storage import archive_key
from services.sector_activity import from_bytes

sector_activity_bp = Blueprint('sector_activity', __name__, url_prefix='/api/sector-activity')


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
