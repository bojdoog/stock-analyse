import os
import json
import functools
from typing import List, Dict, Any, Optional

from utils.csv_parser import (
    parse_kline_csv,
    parse_moneyflow_csv,
    get_data_list,
    get_file_content,
)


class DataService:
    """数据服务层 - 处理所有数据访问逻辑"""
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        # 内存缓存
        self._cache: Dict[str, Any] = {}
    
    def _cached(self, key: str, loader):
        """带缓存的加载器"""
        if key not in self._cache:
            self._cache[key] = loader()
        return self._cache[key]
    
    def get_kline_data(self, category: str, code: str) -> List[Dict[str, Any]]:
        """获取 K 线数据
        
        Args:
            category: 数据分类 (stock, etf, index)
            code: 股票/ETF/指数代码
            
        Returns:
            K 线数据列表
        """
        file_path = self._resolve_path(category, code)
        if not file_path:
            return []
        return parse_kline_csv(file_path)
    
    def get_kline_raw(self, category: str, code: str) -> Optional[str]:
        """获取原始 CSV 内容"""
        file_path = self._resolve_path(category, code)
        if not file_path:
            return None
        return get_file_content(self.data_dir, os.path.relpath(file_path, self.data_dir))
    
    def get_data_list(self, category: str) -> List[Dict[str, str]]:
        """获取指定分类下的文件列表"""
        valid_categories = ['stock', 'etf', 'index']
        if category not in valid_categories:
            return []
        return get_data_list(self.data_dir, category)
    
    def get_all_data_list(self) -> Dict[str, List[Dict[str, str]]]:
        """获取所有分类的数据列表"""
        categories = ['stock', 'etf', 'index']
        result = {}
        for cat in categories:
            result[cat] = get_data_list(self.data_dir, cat)
        return result
    
    def get_moneyflow_data(self, flow_type: str) -> List[Dict[str, Any]]:
        """获取资金流向数据（带缓存）
        
        Args:
            flow_type: 资金流向类型
                - ind_dc: 东财行业资金流向
                - cnt_ths: 同花顺概念资金流向
                - ind_ths: 同花顺行业资金流向
        """
        return self._cached(f'moneyflow_{flow_type}', lambda: self._load_moneyflow(flow_type))
    
    def get_moneyflow_batch(self, types: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """批量获取资金流向数据
        
        Args:
            types: 资金流向类型列表，如 ['ind_dc', 'cnt_ths']
            
        Returns:
            { type: data, ... }
        """
        result = {}
        for t in types:
            result[t] = self.get_moneyflow_data(t)
        return result
    
    def get_all_sector_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有 ETF 和 Index 板块数据
        
        Returns:
            {
                'etf_data': [{ 'name': str, 'id': str, 'data': [...] }, ...],
                'index_data': [{ 'name': str, 'id': str, 'data': [...] }, ...]
            }
        """
        return self._cached('sector_data', self._load_all_sector_data)
    
    def _load_moneyflow(self, flow_type: str) -> List[Dict[str, Any]]:
        """实际加载资金流向数据"""
        type_map = {
            'ind_dc': 'moneyflow_ind_dc',
            'cnt_ths': 'moneyflow_cnt_ths',
            'ind_ths': 'moneyflow_ind_ths',
        }
        
        dir_name = type_map.get(flow_type)
        if not dir_name:
            return []
        
        dir_path = os.path.join(self.data_dir, dir_name)
        if not os.path.isdir(dir_path):
            return []
        
        all_data = []
        for filename in sorted(os.listdir(dir_path)):
            if filename.endswith('.csv'):
                file_path = os.path.join(dir_path, filename)
                data = parse_moneyflow_csv(file_path)
                all_data.extend(data)
        
        return all_data
    
    def _load_all_sector_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """实际加载所有 ETF 和 Index 数据"""
        # ETF 数据
        etf_data = []
        etf_dir = os.path.join(self.data_dir, 'etf')
        if os.path.isdir(etf_dir):
            for filename in sorted(os.listdir(etf_dir)):
                if not filename.endswith('.csv'):
                    continue
                # 文件名格式: 510050_上证50ETF.csv
                parts = filename.replace('.csv', '').split('_', 1)
                code = parts[0]
                name = parts[1] if len(parts) > 1 else code
                file_path = os.path.join(etf_dir, filename)
                data = parse_kline_csv(file_path)
                etf_data.append({
                    'name': name,
                    'id': code,
                    'data': data,
                })
        
        # Index 数据
        index_data = []
        index_dir = os.path.join(self.data_dir, 'index')
        if os.path.isdir(index_dir):
            for filename in sorted(os.listdir(index_dir)):
                if not filename.endswith('.csv'):
                    continue
                parts = filename.replace('.csv', '').split('_', 1)
                code = parts[0]
                name = parts[1] if len(parts) > 1 else code
                file_path = os.path.join(index_dir, filename)
                data = parse_kline_csv(file_path)
                index_data.append({
                    'name': name,
                    'id': f'sh{code}',
                    'data': data,
                })
        
        return {
            'etf_data': etf_data,
            'index_data': index_data,
        }
    
    def get_moneyflow_file_list(self, flow_type: str) -> List[str]:
        """获取资金流向数据文件列表"""
        type_map = {
            'ind_dc': 'moneyflow_ind_dc',
            'cnt_ths': 'moneyflow_cnt_ths',
            'ind_ths': 'moneyflow_ind_ths',
        }
        
        dir_name = type_map.get(flow_type)
        if not dir_name:
            return []
        
        dir_path = os.path.join(self.data_dir, dir_name)
        if not os.path.isdir(dir_path):
            return []
        
        return [f for f in sorted(os.listdir(dir_path)) if f.endswith('.csv')]
    
    def get_moneyflow_by_file(self, flow_type: str, filename: str) -> List[Dict[str, Any]]:
        """获取指定资金流向文件的数据"""
        type_map = {
            'ind_dc': 'moneyflow_ind_dc',
            'cnt_ths': 'moneyflow_cnt_ths',
            'ind_ths': 'moneyflow_ind_ths',
        }
        
        dir_name = type_map.get(flow_type)
        if not dir_name:
            return []
        
        file_path = os.path.join(self.data_dir, dir_name, filename)
        if not os.path.exists(file_path):
            return []
        
        return parse_moneyflow_csv(file_path)
    
    def get_amv_data(self) -> List[Dict[str, Any]]:
        """获取活跃市值数据 (0AMV)"""
        file_path = os.path.join(self.data_dir, '0AMV-2013-2026.csv')
        if not os.path.exists(file_path):
            return []
        return parse_kline_csv(file_path)
    
    def get_data_categories(self) -> List[Dict[str, Any]]:
        """获取所有可用的数据分类"""
        categories = []
        cat_info = {
            'stock': {'name': '个股', 'description': 'A股个股日K数据'},
            'etf': {'name': 'ETF', 'description': 'ETF基金日K数据'},
            'index': {'name': '指数', 'description': '主要指数日K数据'},
            'moneyflow_ind_dc': {'name': '东财行业资金流向', 'description': '东方财富行业资金流向数据'},
            'moneyflow_cnt_ths': {'name': '同花顺概念资金流向', 'description': '同花顺概念板块资金流向'},
            'moneyflow_ind_ths': {'name': '同花顺行业资金流向', 'description': '同花顺行业资金流向'},
        }
        
        for cat, info in cat_info.items():
            cat_path = os.path.join(self.data_dir, cat)
            count = 0
            if os.path.isdir(cat_path):
                count = len([f for f in os.listdir(cat_path) if f.endswith('.csv')])
            categories.append({
                'key': cat,
                'name': info['name'],
                'description': info['description'],
                'fileCount': count,
            })
        
        return categories
    
    def _resolve_path(self, category: str, code: str) -> Optional[str]:
        """解析文件路径"""
        # 处理 etf 目录下的特殊命名格式
        if category == 'etf':
            # ETF 文件名可能包含中文，如 510050_上证50ETF.csv
            etf_dir = os.path.join(self.data_dir, 'etf')
            if os.path.isdir(etf_dir):
                for filename in os.listdir(etf_dir):
                    if filename.startswith(code) and filename.endswith('.csv'):
                        return os.path.join(etf_dir, filename)
            return None
        
        # 处理 index 目录
        if category == 'index':
            index_dir = os.path.join(self.data_dir, 'index')
            if os.path.isdir(index_dir):
                for filename in os.listdir(index_dir):
                    if filename.startswith(code) and filename.endswith('.csv'):
                        return os.path.join(index_dir, filename)
            return None
        
        # 处理 stock 目录
        file_path = os.path.join(self.data_dir, category, f'{code}.csv')
        if os.path.exists(file_path):
            return file_path
        
        return None
