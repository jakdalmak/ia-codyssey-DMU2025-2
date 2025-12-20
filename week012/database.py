# database.py
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = 'sqlite:///./board.db'

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={'check_same_thread': False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


@contextmanager
def get_db_cm():
    """
    contextlib.contextmanager를 사용한 DB 세션 컨텍스트 매니저입니다.

    일반 파이썬 코드에서 예시:
        from database import get_db_cm

        with get_db_cm() as db:
            db.query(...)

    사용이 끝나면 자동으로 db.close()가 호출됩니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    """
    FastAPI Depends에서 사용할 DB 의존성 함수입니다.

    내부적으로 contextlib 기반 get_db_cm()을 사용하여
    요청마다 세션을 열고, 응답이 끝난 뒤 자동으로 세션을 닫습니다.

    라우터에서는 다음과 같이 사용합니다.
        db: Session = Depends(get_db)
    """
    with get_db_cm() as db:
        yield db
