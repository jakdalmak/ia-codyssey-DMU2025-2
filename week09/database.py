# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite 파일 이름 (board.db 라고 저장)
SQLALCHEMY_DATABASE_URL = "sqlite:///./board.db"

# SQLite를 쓰는 경우 check_same_thread 옵션 필요
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# 여기서 autocommit=False 설정 (과제 요구사항)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# 베이스 클래스 (모든 모델의 부모)
Base = declarative_base()
