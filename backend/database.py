import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Por padrão, roda em SQLite (um arquivo só, zero instalação) — ótimo pra
# começar rápido e testar. Quando quiser Postgres (mais robusto pra vários
# usuários ao mesmo tempo), defina no .env:
#   DATABASE_URL=postgresql://usuario:senha@localhost:5432/agua_esgoto
# O resto do sistema funciona idêntico nos dois — só muda essa variável.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./siga.db")

argumentos_conexao = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=argumentos_conexao)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
