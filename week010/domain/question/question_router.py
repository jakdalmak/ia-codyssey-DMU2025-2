# domain/question/question_router.py
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Question

router = APIRouter(
    prefix='/api/question',
    tags=['question'],
)


@router.get('/question-list', summary='질문 목록 조회')
def question_list(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """
    질문 목록을 조회한다.

    - SQLite(board.db)에 저장된 question 테이블에서 모든 레코드를 조회한다.
    - ORM(Question 모델)을 이용해서 데이터를 가져온다.
    - 결과는 JSON 배열 형태로 반환한다.
    """
    questions = (
        db.query(Question)
        .order_by(Question.create_date.desc())
        .all()
    )

    result: List[Dict[str, Any]] = []
    for question in questions:
        result.append(
            {
                'id': question.id,
                'subject': question.subject,
                'content': question.content,
                'create_date': question.create_date,
            },
        )
    return result
