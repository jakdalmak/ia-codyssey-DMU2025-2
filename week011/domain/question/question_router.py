# domain/question/question_router.py
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Question
from .question_schema import QuestionSchema

router = APIRouter(
    prefix='/api/question',
    tags=['question'],
)


@router.get(
    '/',
    response_model=List[QuestionSchema],
    summary='질문 목록 조회',
)
def question_list(db: Session = Depends(get_db)) -> List[Question]:
    """
    질문 목록을 조회합니다.

    - contextlib 기반 get_db_cm()을 감싼 get_db 의존성을 통해
      요청마다 DB 세션을 주입받습니다.
    - SQLAlchemy ORM(Question 모델)을 이용해 question 테이블 전체를 조회합니다.
    - Pydantic QuestionSchema (orm_mode=True)를 통해 응답 JSON을 생성합니다.
    """
    questions = (
        db.query(Question)
        .order_by(Question.create_date.desc())
        .all()
    )
    return questions
