import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 数据目录 - 指向项目根目录的 data 文件夹
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')

# 前端构建产物目录
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'stock-line', 'dist')

# Flask 配置
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'stock-analyse-secret-key')
    DEBUG = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    
    # 数据目录
    DATA_DIR = DATA_DIR
    FRONTEND_DIR = FRONTEND_DIR
    DATABASE_PATH = os.environ.get(
        'DATABASE_PATH', 'auto'
    )
    
    # 允许的 CORS 来源
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
