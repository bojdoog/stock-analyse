import os
import sys
import threading
import datetime
import json
import urllib.request

from flask import Flask, send_from_directory, send_file, abort, jsonify, request
from flask_cors import CORS

# 将当前目录加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from routes.api import api_bp

# ---------- 访问日志 ----------
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

# IP地理位置缓存
_ip_location_cache = {}

def _get_real_ip():
    """获取真实客户端IP（处理nginx反向代理）"""
    xff = request.headers.get('X-Forwarded-For')
    if xff:
        return xff.split(',')[0].strip()
    xri = request.headers.get('X-Real-IP')
    if xri:
        return xri.strip()
    return request.remote_addr or '-'

def _get_ip_location(ip):
    """查询IP归属地（带缓存）"""
    if ip in _ip_location_cache:
        return _ip_location_cache[ip]
    if ip in ('127.0.0.1', '::1', 'localhost'):
        _ip_location_cache[ip] = '本地'
        return '本地'
    try:
        url = f'http://ip-api.com/json/{ip}?lang=zh-CN&fields=city,isp,country'
        with urllib.request.urlopen(url, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            if data.get('status') == 'success':
                parts = [data.get('country', ''), data.get('city', ''), data.get('isp', '')]
                loc = ' '.join(p for p in parts if p)
                _ip_location_cache[ip] = loc or '未知'
                return _ip_location_cache[ip]
    except Exception:
        pass
    _ip_location_cache[ip] = '-'
    return '-'

def _write_access_log(line: str):
    """写入访问日志文件"""
    log_file = os.path.join(LOG_DIR, 'user_login.log')
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass  # 写入失败不影响主流程
# ----------------------------


def create_app(config_class=Config):
    """创建 Flask 应用工厂函数"""
    app = Flask(__name__, static_folder=None)
    
    # 加载配置
    app.config.from_object(config_class)
    
    # 启用 CORS（允许跨域访问）
    CORS(app, resources={
        r'/api/*': {'origins': config_class.CORS_ORIGINS},
        r'/data/*': {'origins': config_class.CORS_ORIGINS},
    })
    
    # 请求访问日志
    @app.before_request
    def log_request():
        # 只记录页面访问，不记录API接口请求
        if request.path.startswith('/api/'):
            return
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ip = _get_real_ip()
        location = _get_ip_location(ip)
        ua = (request.headers.get('User-Agent', '-')[:60])
        line = f'[ACCESS] {now} | {ip} | {location} | {ua}'
        print(line)
        _write_access_log(line)
    
    # 注册 API 蓝图
    app.register_blueprint(api_bp)
    
    # 数据文件路由 - 直接提供 CSV 静态文件访问
    @app.route('/data/<path:filepath>')
    def serve_data_file(filepath):
        """提供数据文件的直接访问，兼容前端 fetch('/data/...') 请求"""
        data_dir = config_class.DATA_DIR
        full_path = os.path.join(data_dir, filepath)
        
        # 安全检查：防止路径穿越
        if not os.path.abspath(full_path).startswith(os.path.abspath(data_dir)):
            abort(403)
        
        if not os.path.exists(full_path):
            abort(404)
        
        # 如果是 CSV 文件，返回纯文本
        if filepath.endswith('.csv'):
            return send_file(
                full_path,
                mimetype='text/csv',
                as_attachment=False,
            )
        
        # 其他文件类型
        return send_file(full_path)
    
    # 提供资金流向的 index.json 索引
    @app.route('/data/<path:dirpath>/index.json')
    def serve_index_json(dirpath):
        """为前端资金流向加载提供目录索引"""
        import json
        full_dir = os.path.join(config_class.DATA_DIR, dirpath)
        
        if not os.path.isdir(full_dir):
            abort(404)
        
        files = [f for f in sorted(os.listdir(full_dir)) if f.endswith('.csv')]
        
        from flask import Response
        return Response(
            json.dumps(files),
            mimetype='application/json'
        )
    
    # 前端静态文件服务（生产模式）
    frontend_dir = config_class.FRONTEND_DIR
    if os.path.isdir(frontend_dir):
        @app.route('/')
        def serve_index():
            return send_from_directory(frontend_dir, 'index.html')
        
        @app.route('/<path:path>')
        def serve_frontend(path):
            file_path = os.path.join(frontend_dir, path)
            if os.path.exists(file_path):
                return send_from_directory(frontend_dir, path)
            # SPA fallback
            return send_from_directory(frontend_dir, 'index.html')
    
    # 错误处理
    @app.errorhandler(404)
    def not_found(error):
        # 如果是 API 请求，返回 JSON
        if request.path.startswith('/api/'):
            return jsonify({
                'code': 404,
                'message': '资源不存在',
            }), 404
        # 否则返回前端首页（SPA fallback）
        if os.path.isdir(frontend_dir):
            return send_from_directory(frontend_dir, 'index.html')
        return jsonify({'error': 'Not Found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'code': 500,
            'message': '服务器内部错误',
        }), 500
    
    return app


# 启动时预热缓存
def _warmup_cache():
    """在后台线程中预热数据缓存"""
    try:
        from routes.api import data_service
        import time
        start = time.time()
        # 预热 sector-data
        data_service.get_all_sector_data()
        # 预热资金流向
        data_service.get_moneyflow_batch(['ind_dc', 'cnt_ths', 'ind_ths'])
        elapsed = time.time() - start
        print(f'[预热] 数据缓存完成，耗时 {elapsed:.2f}s')
    except Exception as e:
        print(f'[预热] 数据缓存失败: {e}')


if __name__ == '__main__':
    app = create_app()
    
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    
    print(f'启动 Flask 服务器...')
    print(f'  地址: http://{host}:{port}')
    print(f'  调试模式: {debug}')
    print(f'  数据目录: {Config.DATA_DIR}')
    print(f'  前端目录: {Config.FRONTEND_DIR}')
    
    if not debug:
        # 生产模式启动时预热缓存
        threading.Thread(target=_warmup_cache, daemon=True).start()
    
    app.run(host=host, port=port, debug=debug)
