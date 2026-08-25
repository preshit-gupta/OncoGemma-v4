import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import settings

db_url = settings.DATABASE_URL

# Fallback to local SQLite if Postgres is unavailable or explicitly selected
if db_url.startswith("sqlite"):
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
else:
    try:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        # Test connection
        with engine.connect() as conn:
            pass
    except Exception as e:
        print(f"[DB Core Warning] Postgres connection failed ({e}). Falling back to local SQLite database.")
        local_db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../oncogemma_local.db"))
        sqlite_url = f"sqlite:///{local_db_path}"
        engine = create_engine(
            sqlite_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
