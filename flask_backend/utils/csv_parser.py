import os
import csv
from typing import List, Dict, Any, Optional


def parse_csv_file(file_path: str) -> List[Dict[str, Any]]:
    """解析 CSV 文件为字典列表"""
    if not os.path.exists(file_path):
        return []
    
    data = []
    encodings = ['utf-8-sig', 'utf-8', 'gbk']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(dict(row))
            break
        except (UnicodeDecodeError, csv.Error):
            data = []
            continue
    
    return data


def parse_kline_csv(file_path: str) -> List[Dict[str, Any]]:
    """解析 K 线数据 CSV（标准格式：date,open,close,high,low,volume[,amount]）"""
    raw_data = parse_csv_file(file_path)
    result = []
    
    for row in raw_data:
        try:
            item = {
                'date': row.get('date', ''),
                'open': _to_float(row.get('open', 0)),
                'close': _to_float(row.get('close', 0)),
                'high': _to_float(row.get('high', 0)),
                'low': _to_float(row.get('low', 0)),
                'volume': _to_float(row.get('volume', 0)),
                'amount': _to_float(row.get('amount', 0)) if 'amount' in row else 0,
            }
            result.append(item)
        except (ValueError, TypeError):
            continue
    
    return result


def parse_moneyflow_csv(file_path: str) -> List[Dict[str, Any]]:
    """解析资金流向 CSV"""
    raw_data = parse_csv_file(file_path)
    result = []
    
    for row in raw_data:
        try:
            item = {
                'date': row.get('date', ''),
                'industry_name': row.get('industry_name', ''),
                'pct_change': _to_float(row.get('pct_change', 0)),
                'close': _to_float(row.get('close_price', row.get('close', 0))),
                'net_inflow': _to_float_or_none(row.get('net_inflow')),
                'net_amount_rate': _to_float(row.get('net_amount_rate', 0)),
                'super_large_inflow': _to_float(row.get('super_large_inflow', 0)),
                'large_inflow': _to_float(row.get('large_inflow', 0)),
                'rank': _to_int(row.get('rank', 0)),
                'etf_code': row.get('etf_code', ''),
                'etf_name': row.get('etf_name', ''),
            }
            result.append(item)
        except (ValueError, TypeError):
            continue
    
    return result


def get_data_list(data_dir: str, category: str) -> List[Dict[str, str]]:
    """获取指定分类下的数据文件列表"""
    category_dir = os.path.join(data_dir, category)
    if not os.path.isdir(category_dir):
        return []
    
    files = []
    for filename in sorted(os.listdir(category_dir)):
        if filename.endswith('.csv'):
            name = filename.replace('.csv', '')
            files.append({
                'code': name,
                'name': name,
                'file': f'{category}/{filename}'
            })
    
    return files


def get_file_content(data_dir: str, relative_path: str) -> Optional[str]:
    """获取文件原始内容"""
    file_path = os.path.join(data_dir, relative_path)
    if not os.path.exists(file_path):
        return None
    
    encodings = ['utf-8-sig', 'utf-8', 'gbk']
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    
    return None


def _to_float(value: Any) -> float:
    """安全转换为 float"""
    if value is None or value == '':
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _to_float_or_none(value: Any) -> Optional[float]:
    """安全转换为 float 或 None"""
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int:
    """安全转换为 int"""
    if value is None or value == '':
        return 0
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0
