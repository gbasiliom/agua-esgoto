"""Alinha o banco existente com os modelos ao ligar o servidor: cria tabelas novas e adiciona
colunas novas em tabelas antigas (SQLite e Postgres). Nunca apaga nem altera dados.
Assim, quem atualiza o código não precisa lembrar de rodar o script de migração."""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn


def alinhar_colunas(engine, base):
    base.metadata.create_all(bind=engine)
    insp = inspect(engine)
    adicionadas = []
    with engine.begin() as conn:
        for tabela in base.metadata.sorted_tables:
            if not insp.has_table(tabela.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela.name)}
            for col in tabela.columns:
                if col.name in existentes or col.primary_key:
                    continue
                definicao = str(CreateColumn(col).compile(dialect=engine.dialect))
                if not col.nullable and col.server_default is None:
                    definicao = definicao.replace(" NOT NULL", "")
                usa_agora = "CURRENT_TIMESTAMP" in definicao.upper() and engine.dialect.name == "sqlite"
                if usa_agora:
                    definicao = definicao.replace("DEFAULT CURRENT_TIMESTAMP", "")
                conn.execute(text(f'ALTER TABLE "{tabela.name}" ADD COLUMN {definicao}'))
                if usa_agora:
                    conn.execute(text(f'UPDATE "{tabela.name}" SET "{col.name}" = CURRENT_TIMESTAMP WHERE "{col.name}" IS NULL'))
                adicionadas.append(f"{tabela.name}.{col.name}")
    return adicionadas
