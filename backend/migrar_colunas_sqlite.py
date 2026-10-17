"""
Alinha um banco SQLite ANTIGO com os modelos atuais, adicionando as colunas que
faltam em tabelas que já existem. Não apaga nem altera nenhum dado.
Seguro rodar quantas vezes quiser.

Uso (dentro da pasta backend, com o venv do backend ativo, servidor parado):
    python migrar_colunas_sqlite.py
"""
from sqlalchemy import text
from sqlalchemy.schema import CreateColumn

from database import engine, Base
import models  # noqa: F401  (registra todas as tabelas)

if engine.dialect.name != "sqlite":
    print("Este script é só para SQLite. Para Postgres use migrar_bd.py.")
    raise SystemExit(0)

# Primeiro cria tabelas inteiras que ainda não existem.
Base.metadata.create_all(bind=engine)

adicionadas = 0
with engine.begin() as conn:
    for tabela in Base.metadata.sorted_tables:
        existentes = {r[1] for r in conn.execute(text(f'PRAGMA table_info("{tabela.name}")'))}
        for col in tabela.columns:
            if col.name in existentes:
                continue
            definicao = str(CreateColumn(col).compile(dialect=engine.dialect))
            if col.primary_key or (not col.nullable and col.default is None and col.server_default is None):
                # SQLite não aceita ADD COLUMN NOT NULL sem valor padrão; relaxa para aceitar nulos.
                definicao = definicao.replace(" NOT NULL", "")
            usa_agora = "CURRENT_TIMESTAMP" in definicao.upper()
            if usa_agora:
                # SQLite não aceita esse padrão ao adicionar coluna: adiciona sem e preenche depois.
                definicao = definicao.replace("DEFAULT CURRENT_TIMESTAMP", "")
            conn.execute(text(f'ALTER TABLE "{tabela.name}" ADD COLUMN {definicao}'))
            if usa_agora:
                conn.execute(text(f'UPDATE "{tabela.name}" SET "{col.name}" = CURRENT_TIMESTAMP '
                                  f'WHERE "{col.name}" IS NULL'))
            print(f"✅ {tabela.name}.{col.name} adicionada.")
            adicionadas += 1

print(f"\nConcluído: {adicionadas} coluna(s) adicionada(s). Nenhum dado foi apagado."
      if adicionadas else "\nO banco já estava alinhado com os modelos. Nada a fazer.")
