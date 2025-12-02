# main.py
from datetime import datetime

from database import SessionLocal
from models import Question


def create_sample_question():
    db = SessionLocal()
    try:
        q = Question(
            subject="첫 번째 질문",
            content="ORM과 Alembic으로 만든 첫 질문입니다.",
            create_date=datetime.utcnow(),
        )
        db.add(q)
        db.commit()      # autocommit=False라서 commit 꼭 필요
        db.refresh(q)

        print("생성된 Question ID:", q.id)
    finally:
        db.close()


if __name__ == "__main__":
    create_sample_question()