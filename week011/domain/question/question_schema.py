# domain/question/question_schema.py
from datetime import datetime

from pydantic import BaseModel


class QuestionSchema(BaseModel):
    id: int
    subject: str
    content: str
    create_date: datetime

    class Config:
        # orm_mode 를 True 로 설정하면 SQLAlchemy 모델 인스턴스를
        # 그대로 반환해도 해당 객체의 속성에서 값을 읽어와서
        # Pydantic 스키마로 변환해 준다.
        orm_mode = True
