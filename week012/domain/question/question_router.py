# domain/question/question_router.py
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from database import get_db
from models import Question
from .question_schema import QuestionSchema, QuestionCreate

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


@router.post(
    '/',
    response_model=QuestionSchema,
    summary='질문 등록',
    status_code=201,
)
def question_create(
    question_in: QuestionCreate,
    db: Session = Depends(get_db),
) -> Question:
    """
    새로운 질문을 등록합니다.

    - 요청 본문은 QuestionCreate 스키마(subject, content 사용)를 따릅니다.
    - 제목과 내용은 빈 문자열을 허용하지 않습니다(min_length=1).
    - SQLAlchemy ORM(Question 모델)을 이용해 SQLite(board.db)에 저장합니다.
    - 저장 후 커밋하고, 생성된 Question 객체를 반환합니다.
    """
    question = Question(
        subject=question_in.subject,
        content=question_in.content,
        create_date=datetime.utcnow(),
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.get(
    '/form',
    response_class=HTMLResponse,
    summary='질문 등록 폼 페이지',
)
def question_form() -> str:
    """
    질문 등록을 위한 간단한 HTML 폼을 반환합니다.
    - 같은 도메인(/api/question/)으로 POST 요청을 보내므로 CORS 문제가 없습니다.
    """
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8" />
        <title>질문 등록</title>
    </head>
    <body>
        <h1>질문 등록</h1>

        <form id="question-form">
            <div>
                <label for="subject">제목</label>
                <input id="subject" name="subject" type="text" required />
            </div>
            <div>
                <label for="content">내용</label><br />
                <textarea id="content" name="content" rows="5" cols="40" required></textarea>
            </div>
            <button type="submit">등록</button>
        </form>

        <h2>응답 결과</h2>
        <pre id="result"></pre>

        <script>
            const form = document.getElementById('question-form');
            const resultEl = document.getElementById('result');

            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const subject = document.getElementById('subject').value;
                const content = document.getElementById('content').value;

                const payload = { subject, content };

                try {
                    const res = await fetch('/api/question/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(payload),
                    });

                    const data = await res.json();
                    resultEl.textContent = JSON.stringify(data, null, 2);
                } catch (err) {
                    resultEl.textContent = '에러: ' + err;
                }
            });
        </script>
    </body>
    </html>
    """
