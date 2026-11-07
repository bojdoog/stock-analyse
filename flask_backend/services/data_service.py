"""Database-backed market queries; data/ is only an export/backup directory."""
from flask import current_app, has_app_context
from market_store import (FLOW_TABLES, PRICE_FIELDS, connect, database_path, date_string,
                          decode, exchange_for, file_content, list_files)
from etf_intraday import load as load_intraday, pull as pull_intraday


class DataService:
    def __init__(self, data_dir=None, db_path=None):
        self.data_dir = data_dir
        self.db_path = db_path

    @property
    def database(self):
        if self.db_path:
            return self.db_path
        return current_app.config['DATABASE_PATH'] if has_app_context() else database_path()

    def _series(self, table, condition, args, start_date=None, end_date=None, limit=None):
        if start_date:
            condition += ' AND date>=?'
            args.append(date_string(start_date))
        if end_date:
            condition += ' AND date<=?'
            args.append(date_string(end_date))
        sql = f"SELECT date,{','.join(PRICE_FIELDS)} FROM {table} WHERE {condition} ORDER BY date"
        if limit and limit > 0:
            sql += ' DESC LIMIT ?'
            args.append(limit)
        with connect(self.database) as db:
            rows = [dict(row) for row in db.execute(sql, args)]
        return list(reversed(rows)) if limit and limit > 0 else rows

    def get_kline_data(self, category, code, start_date=None, end_date=None, limit=None):
        if category not in ('stock', 'etf', 'index', 'etf_hj'):
            return []
        # 带上 exchange 才能命中主键 (category,exchange,code,date) 前缀。
        return self._series('daily_bars', 'category=? AND exchange=? AND code=?',
                            [category, exchange_for(category, code), code], start_date, end_date, limit)

    def get_huijin_etfs(self):
        """汇金系宽基 ETF 最新交易日行情，按成交量从大到小排列。"""
        with connect(self.database) as db:
            rows = db.execute(
                "SELECT code, name, date, close, volume, amount, change_pct FROM ("
                " SELECT i.code, i.name, b.date, b.close, b.volume, b.amount,"
                " (b.close / LAG(b.close) OVER (PARTITION BY b.code ORDER BY b.date) - 1) * 100 AS change_pct,"
                " ROW_NUMBER() OVER (PARTITION BY b.code ORDER BY b.date DESC) AS rn"
                " FROM daily_bars b JOIN instruments i"
                " ON i.category = b.category AND i.code = b.code"
                " WHERE b.category = 'etf_hj') t WHERE rn = 1 ORDER BY volume DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item.pop('rn', None)
            item['change_pct'] = None if item['change_pct'] is None else round(item['change_pct'], 2)
            result.append(item)
        return result

    def get_etf_intraday(self, code, date):
        """单只汇金系 ETF 某日的 1 分钟走势；库里没有该日时就地补拉新浪，仍无则返回空。"""
        requested = date
        from_sina = 'N'
        with connect(self.database) as db:
            rows = load_intraday(db, code, date)
            if not rows and pull_intraday(db, code, date):
                from_sina = 'Y'
                rows = load_intraday(db, code, date)
            name = db.execute("SELECT name FROM instruments WHERE category='etf_hj' AND code=?",
                              (code,)).fetchone()
            previous = db.execute("SELECT date, close FROM daily_bars WHERE category='etf_hj' AND code=? "
                                  "AND date<? ORDER BY date DESC LIMIT 1", (code, date)).fetchone()
            previous_date = db.execute("SELECT max(date) FROM etf_intraday WHERE code=? AND date<?",
                                       (code, date)).fetchone()[0]
            next_date = db.execute("SELECT min(date) FROM etf_intraday WHERE code=? AND date>?",
                                   (code, date)).fetchone()[0]
            bounds = db.execute("SELECT min(date), max(date) FROM etf_intraday WHERE code=?",
                                (code,)).fetchone()
        return {
            'data': rows,
            'meta': {
                'code': code,
                'name': name[0] if name else code,
                'date': date,
                'requestedDate': requested,
                'fromSina': from_sina,
                'availableFrom': bounds[0] if bounds else None,
                'availableTo': bounds[1] if bounds else None,
                'count': len(rows),
                'previousClose': previous[1] if previous else None,
                'previousCloseDate': previous[0] if previous else None,
                'previousDate': previous_date,
                'nextDate': next_date,
            },
        }

    def get_b1_picks(self, date=None, refresh=False):
        """B1 选股结果；首次按日期计算并落库，之后直接读缓存。"""
        from b1_selector import picks_for
        from stock_meta import describe
        day, rows, computed = picks_for(date, refresh)
        # 补上股票名称/板块/行业，页面直接展示，不用再单独查一次。
        data = [{**row, **describe(row['code'])} for row in rows]
        return {'data': data, 'meta': {'date': day, 'count': len(rows), 'computed': computed}}

    def get_b1_history(self):
        """B1 选股历史：按日期由近到远，带当天条件与股票数。"""
        from market_store import connect
        from b1_selector import history
        with connect() as db:
            return history(db)

    def get_indicator_data(self, indicator_id, start_date=None, end_date=None, limit=None):
        return self._series('indicator_daily', 'indicator_id=?', [indicator_id], start_date, end_date, limit)

    def get_amv_data(self, start_date=None, end_date=None, limit=None):
        with connect(self.database) as db:
            row = db.execute("SELECT id FROM indicators WHERE code='0AMV'").fetchone()
        return self.get_indicator_data(row[0], start_date, end_date, limit) if row else []

    def get_data_list(self, category):
        if category not in ('stock', 'etf', 'index'):
            return []
        if category == 'etf':
            from etf_catalog import list_etfs
            return list_etfs(self.database)
        with connect(self.database) as db:
            return [dict(row) for row in db.execute(
                'SELECT code,name,source_path AS file FROM instruments WHERE category=? ORDER BY source_path', (category,))]

    def get_all_data_list(self):
        return {category: self.get_data_list(category) for category in ('stock', 'etf', 'index')}

    def get_file_bytes(self, relative_path):
        if relative_path == 'etf/index.json':
            import json
            return json.dumps(list_files('etf', self.database), ensure_ascii=False).encode('utf-8')
        return file_content(relative_path, self.database)

    def get_kline_raw(self, category, code):
        with connect(self.database) as db:
            row = db.execute('SELECT source_path FROM instruments WHERE category=? AND code=?', (category, code)).fetchone()
        content = self.get_file_bytes(row[0]) if row else None
        return decode(content) if content is not None else None

    def get_all_sector_data(self):
        result = {}
        for category in ('etf', 'index'):
            result[category + '_data'] = [
                {'name': item['name'], 'id': ('sh' if category == 'index' else '') + item['code'],
                 'data': self.get_kline_data(category, item['code'])} for item in self.get_data_list(category)]
        return result

    def get_moneyflow_data(self, flow_type, start_date=None, end_date=None, industry=None, limit=None, filename=None):
        table = FLOW_TABLES.get(flow_type)
        if not table:
            return []
        filters, values = ['1=1'], []
        if start_date:
            filters.append('date>=?')
            values.append(date_string(start_date))
        if end_date:
            filters.append('date<=?')
            values.append(date_string(end_date))
        if industry:
            filters.append('instr(industry_name,?)>0')
            values.append(industry)
        if filename:
            filters.append('source_path=?')
            values.append(f'{table}/{filename}')
        sql = f"SELECT * FROM {table} WHERE {' AND '.join(filters)} ORDER BY source_path,`row_number`"
        if limit and limit > 0:
            sql = f"SELECT * FROM {table} WHERE {' AND '.join(filters)} ORDER BY source_path DESC,`row_number` DESC LIMIT ?"
            values.append(limit)
        with connect(self.database) as db:
            rows = [dict(row) for row in db.execute(sql, values)]
        # Resolve historic snapshots against today's registry as well. Disabled
        # ETF mappings must not leak back into rankings from archived flow rows.
        from etf_catalog import sector_mapping
        mapping = sector_mapping(flow_type, self.database)
        for row in rows:
            etf = mapping.get(row['industry_name'], {})
            row['etf_code'] = etf.get('code', '')
            row['etf_name'] = etf.get('name', '')
        if limit and limit > 0:
            rows.reverse()
        for row in rows:
            for key in ('sector_key', 'occurrence', 'source_path', 'row_number'):
                row.pop(key)
            row['date'] = row['date'].replace('-', '')
            if flow_type != 'ind_dc':
                row['close'] = row['close_price']
            # Preserve existing API compatibility; SQL retains NULL/source fields.
            for key in ('pct_change', 'close', 'net_amount_rate', 'super_large_inflow', 'large_inflow', 'rank'):
                if row[key] is None:
                    row[key] = 0
        return rows

    def get_moneyflow_batch(self, types):
        return {kind: self.get_moneyflow_data(kind) for kind in types}

    def get_moneyflow_file_list(self, flow_type):
        return list_files(FLOW_TABLES[flow_type], self.database) if flow_type in FLOW_TABLES else []

    def get_moneyflow_by_file(self, flow_type, filename):
        return self.get_moneyflow_data(flow_type, filename=filename)

    def get_data_categories(self):
        names = {'stock': '个股', 'etf': 'ETF', 'index': '指数', 'core_index': '核心指标',
                 'moneyflow_ind_dc': '东财行业资金流向', 'moneyflow_cnt_ths': '同花顺概念资金流向',
                 'moneyflow_ind_ths': '同花顺行业资金流向'}
        with connect(self.database) as db:
            counts = {row[0]: row[1] for row in db.execute(
                "SELECT category,COUNT(*) FROM source_files WHERE path LIKE '%.csv' GROUP BY category")}
        return [{'key': key, 'name': name, 'description': name, 'fileCount': counts.get(key, 0)}
                for key, name in names.items()]
