"""Database-backed market queries; data/ is only an export/backup directory."""
from flask import current_app, has_app_context
from market_store import (FLOW_TABLES, PRICE_FIELDS, connect, database_path, date_string,
                          decode, file_content, list_files)


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
        if category not in ('stock', 'etf', 'index'):
            return []
        return self._series('daily_bars', 'category=? AND code=?', [category, code], start_date, end_date, limit)

    def get_indicator_data(self, indicator_id, start_date=None, end_date=None, limit=None):
        return self._series('indicator_daily', 'indicator_id=?', [indicator_id], start_date, end_date, limit)

    def get_amv_data(self, start_date=None, end_date=None, limit=None):
        with connect(self.database) as db:
            row = db.execute("SELECT id FROM indicators WHERE code='0AMV'").fetchone()
        return self.get_indicator_data(row[0], start_date, end_date, limit) if row else []

    def get_data_list(self, category):
        if category not in ('stock', 'etf', 'index'):
            return []
        with connect(self.database) as db:
            return [dict(row) for row in db.execute(
                'SELECT code,name,source_path AS file FROM instruments WHERE category=? ORDER BY source_path', (category,))]

    def get_all_data_list(self):
        return {category: self.get_data_list(category) for category in ('stock', 'etf', 'index')}

    def get_file_bytes(self, relative_path):
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
