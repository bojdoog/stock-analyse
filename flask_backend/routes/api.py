from flask import Blueprint, jsonify, request, send_file
from services.data_service import DataService
from config import Config
import os

api_bp = Blueprint('api', __name__, url_prefix='/api')

data_service = DataService(Config.DATA_DIR)


@api_bp.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'service': 'stock-analyse-api',
        'dataDir': Config.DATA_DIR,
    })


@api_bp.route('/categories', methods=['GET'])
def get_categories():
    """获取所有可用的数据分类"""
    categories = data_service.get_data_categories()
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': categories,
    })


@api_bp.route('/list/<category>', methods=['GET'])
def get_data_list(category):
    """获取指定分类的数据文件列表
    
    Path Parameters:
        category: stock | etf | index
        
    Query Parameters:
        page: 页码 (可选，默认全部)
        size: 每页数量 (可选)
    """
    data_list = data_service.get_data_list(category)
    
    page = request.args.get('page', type=int)
    size = request.args.get('size', type=int)
    
    if page and size:
        start = (page - 1) * size
        end = start + size
        data_list = data_list[start:end]
        total = len(data_service.get_data_list(category))
        return jsonify({
            'code': 0,
            'message': 'success',
            'data': data_list,
            'pagination': {
                'page': page,
                'size': size,
                'total': total,
            }
        })
    
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': data_list,
    })


@api_bp.route('/lists', methods=['GET'])
def get_all_data_lists():
    """获取所有分类的数据列表"""
    data = data_service.get_all_data_list()
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': data,
    })


@api_bp.route('/kline/<category>/<code>', methods=['GET'])
def get_kline_data(category, code):
    """获取 K 线数据 (JSON 格式)
    
    Path Parameters:
        category: stock | etf | index
        code: 股票/ETF/指数代码
        
    Query Parameters:
        start_date: 开始日期 (可选, 格式: YYYY-MM-DD)
        end_date: 结束日期 (可选, 格式: YYYY-MM-DD)
        limit: 限制返回条数 (可选)
    """
    data = data_service.get_kline_data(category, code)
    
    # 日期过滤
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if start_date:
        data = [d for d in data if d['date'] >= start_date]
    if end_date:
        data = [d for d in data if d['date'] <= end_date]
    
    # 限制数量
    limit = request.args.get('limit', type=int)
    if limit and limit > 0:
        data = data[-limit:]
    
    if not data:
        return jsonify({
            'code': 404,
            'message': f'未找到 {category}/{code} 的数据',
            'data': [],
        }), 404
    
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': data,
        'meta': {
            'category': category,
            'code': code,
            'count': len(data),
            'startDate': data[0]['date'] if data else None,
            'endDate': data[-1]['date'] if data else None,
        }
    })


@api_bp.route('/kline/<category>/<code>/csv', methods=['GET'])
def get_kline_csv(category, code):
    """获取 K 线数据 (原始 CSV 格式)
    
    用于兼容前端现有的 fetch('/data/...') 请求
    """
    content = data_service.get_kline_raw(category, code)
    if content is None:
        return jsonify({
            'code': 404,
            'message': f'未找到 {category}/{code} 的数据文件',
        }), 404
    
    from flask import Response
    return Response(
        content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={code}.csv'}
    )


@api_bp.route('/amv', methods=['GET'])
def get_amv_data():
    """获取活跃市值数据
    
    Query Parameters:
        start_date: 开始日期 (可选)
        end_date: 结束日期 (可选)
        limit: 限制返回条数 (可选)
    """
    data = data_service.get_amv_data()
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    limit = request.args.get('limit', type=int)
    
    if start_date:
        data = [d for d in data if d['date'] >= start_date]
    if end_date:
        data = [d for d in data if d['date'] <= end_date]
    if limit and limit > 0:
        data = data[-limit:]
    
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': data,
        'meta': {
            'count': len(data),
            'startDate': data[0]['date'] if data else None,
            'endDate': data[-1]['date'] if data else None,
        }
    })


@api_bp.route('/moneyflow/<flow_type>', methods=['GET'])
def get_moneyflow_data(flow_type):
    """获取资金流向数据
    
    Path Parameters:
        flow_type: ind_dc | cnt_ths | ind_ths
        
    Query Parameters:
        start_date: 开始日期 (可选)
        end_date: 结束日期 (可选)
        industry: 行业名称过滤 (可选)
        limit: 限制返回条数 (可选)
    """
    valid_types = ['ind_dc', 'cnt_ths', 'ind_ths']
    if flow_type not in valid_types:
        return jsonify({
            'code': 400,
            'message': f'无效的资金流向类型: {flow_type}，支持: {", ".join(valid_types)}',
        }), 400
    
    data = data_service.get_moneyflow_data(flow_type)
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    industry = request.args.get('industry')
    limit = request.args.get('limit', type=int)
    
    if start_date:
        data = [d for d in data if d['date'] >= start_date]
    if end_date:
        data = [d for d in data if d['date'] <= end_date]
    if industry:
        data = [d for d in data if industry in d.get('industry_name', '')]
    if limit and limit > 0:
        data = data[-limit:]
    
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': data,
        'meta': {
            'flowType': flow_type,
            'count': len(data),
        }
    })


@api_bp.route('/moneyflow/batch', methods=['GET'])
def get_moneyflow_batch():
    """批量获取资金流向数据（支持多选）
    
    Query Parameters:
        types: 类型列表，逗号分隔，如 ind_dc,cnt_ths,ind_ths
              可选值: ind_dc | cnt_ths | ind_ths
    """
    types_param = request.args.get('types', 'ind_dc,cnt_ths,ind_ths')
    valid_types = {'ind_dc', 'cnt_ths', 'ind_ths'}
    types = [t.strip() for t in types_param.split(',') if t.strip() in valid_types]
    
    if not types:
        return jsonify({
            'code': 400,
            'message': '请指定有效的资金流向类型，支持: ind_dc, cnt_ths, ind_ths',
        }), 400
    
    data = data_service.get_moneyflow_batch(types)
    
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': data,
        'meta': {
            'types': types,
            'counts': {t: len(data[t]) for t in types},
        }
    })


@api_bp.route('/sector-data', methods=['GET'])
def get_sector_data():
    """获取所有 ETF 和 Index 板块数据
    
    Query Parameters:
        fields: 返回字段，逗号分隔，如 etf_data,index_data（默认都返回）
    """
    fields_param = request.args.get('fields', 'etf_data,index_data')
    all_data = data_service.get_all_sector_data()
    
    fields = [f.strip() for f in fields_param.split(',') if f.strip() in all_data]
    if not fields:
        fields = ['etf_data', 'index_data']
    
    result = {f: all_data[f] for f in fields}
    
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': result,
        'meta': {
            'fields': fields,
            'counts': {f: len(result[f]) for f in fields},
        }
    })


@api_bp.route('/moneyflow/<flow_type>/files', methods=['GET'])
def get_moneyflow_files(flow_type):
    """获取资金流向数据文件列表"""
    files = data_service.get_moneyflow_file_list(flow_type)
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': files,
    })


@api_bp.route('/moneyflow/<flow_type>/file/<filename>', methods=['GET'])
def get_moneyflow_by_file(flow_type, filename):
    """获取指定资金流向文件的数据"""
    data = data_service.get_moneyflow_by_file(flow_type, filename)
    return jsonify({
        'code': 0,
        'message': 'success',
        'data': data,
        'meta': {
            'flowType': flow_type,
            'filename': filename,
            'count': len(data),
        }
    })
