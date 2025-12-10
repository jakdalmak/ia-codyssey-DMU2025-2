# main.py
from datetime import datetime

from fastapi import FastAPI

from database import Base, SessionLocal, engine
from domain.question.question_router import router as question_router
from models import Question

# alembic으로 이미 테이블을 만든 상태라면 필수는 아니지만,
# 기존 테이블이 있으면 그대로 두고, 없으면 새로 만들어준다.
Base.metadata.create_all(bind=engine)

app = FastAPI()


@app.get('/', summary='헬스 체크용 기본 엔드포인트')
def read_root():
    return {'message': 'Board API is running.'}


# question 라우터 등록
app.include_router(question_router)


def create_sample_question() -> None:
    """
    초기 테스트용 질문 1개를 DB에 넣는 유틸 함수입니다.
    main.py를 직접 실행했을 때만 동작합니다.
    """
    db = SessionLocal()
    try:
        q = Question(
            subject='첫 번째 질문',
            content='ORM과 Alembic으로 만든 첫 질문입니다.',
            create_date=datetime.utcnow(),
        )
        db.add(q)
        db.commit()
        db.refresh(q)
        print('생성된 Question ID:', q.id)
    finally:
        db.close()


if __name__ == '__main__':
    # python main.py 로 실행했을 때만 샘플 데이터를 넣습니다.
    create_sample_question()
