# check_db.py

from sqlalchemy import inspect
from database import engine

def show_tables():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print("📋 현재 DB에 존재하는 테이블 목록:")
    for name in tables:
        print("-", name)

if __name__ == "__main__":
    show_tables()