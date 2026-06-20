import os

# 데이터베이스 설정
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_PATH = os.path.join(basedir, 'gym_management.db')

# Flask 설정
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'gym-management-secret-key-2026')
    JSON_AS_ASCII = False  # 한글 깨짐 방지