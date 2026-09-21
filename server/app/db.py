from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import DB_URL
from .models import Base

engine = create_engine(DB_URL, future=True, connect_args={"check_same_thread": False})
Session = sessionmaker(engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)
