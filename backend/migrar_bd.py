"""
Migração incremental do banco — adiciona colunas/tabelas novas sem apagar
nada que já existe. Seguro rodar quantas vezes quiser.

Funciona tanto com PostgreSQL quanto com SQLite (detecta sozinho qual banco
está configurado no DATABASE_URL e ajusta o que for preciso).

Uso:
    cd backend
    venv\\Scripts\\activate
    python migrar_bd.py
"""
from sqlalchemy import text
from database import engine, Base
import models  # garante que os modelos novos (tabelas de estoque) sejam conhecidos

EH_POSTGRES = engine.dialect.name == "postgresql"
EH_SQLITE = engine.dialect.name == "sqlite"

print(f"Banco detectado: {engine.dialect.name}")

if EH_POSTGRES:
    # --- Só faz sentido em Postgres: banco já existia antes dessas colunas/tabelas existirem ---
    COLUNAS_NOVAS = {
        "chamados": {
            "checklist": "TEXT",
            "materiais_utilizados": "TEXT",
            "local_atendimento": "VARCHAR(30)",
        },
        "usuarios": {
            "localidade": "VARCHAR(30)",
        },
        "clientes": {
            "localidade": "VARCHAR(30)",
            "status_cadastro": "VARCHAR(15) DEFAULT 'aprovado'",
        },
    }

    with engine.connect() as conn:
        for tabela, colunas in COLUNAS_NOVAS.items():
            for nome_coluna, tipo in colunas.items():
                resultado = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :tabela AND column_name = :nome"
                ), {"tabela": tabela, "nome": nome_coluna})

                if resultado.first():
                    print(f"→ {tabela}.{nome_coluna} já existia.")
                else:
                    conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {nome_coluna} {tipo}"))
                    conn.commit()
                    print(f"✅ {tabela}.{nome_coluna} adicionada.")

    # Tabela "faturas" antiga (do esqueleto inicial, nunca usada, schema diferente)
    with engine.connect() as conn:
        tabela_existe = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'faturas'"
        )).first()
        if tabela_existe:
            tem_linhas = conn.execute(text("SELECT COUNT(*) FROM faturas")).scalar()
            if tem_linhas == 0:
                conn.execute(text("DROP TABLE faturas"))
                conn.commit()
                print("→ Tabela 'faturas' antiga (vazia, schema desatualizado) removida.")
            else:
                print("⚠ Tabela 'faturas' já existe E tem dados — não mexi nela.")
else:
    print("→ Banco SQLite: pulando os ajustes específicos de Postgres (não fazem sentido aqui —")
    print("  um arquivo SQLite novo já nasce com o schema certo direto do create_all abaixo).")

# Tabelas novas em geral — funciona igual nos dois bancos.
Base.metadata.create_all(bind=engine)
print("✅ Tabelas conferidas/criadas (se ainda não existiam).")

# Tarifas de teste — usa o ORM (em vez de SQL cru) justamente pra funcionar
# igual em Postgres e SQLite, sem se preocupar com sintaxe de cada um.
from database import SessionLocal
db = SessionLocal()
if db.query(models.TarifaFaixa).count() == 0:
    db.add_all([
        models.TarifaFaixa(consumo_min=0, consumo_max=10, valor_m3=3.50, percentual_esgoto=80, ativo=True),
        models.TarifaFaixa(consumo_min=10, consumo_max=20, valor_m3=5.80, percentual_esgoto=80, ativo=True),
        models.TarifaFaixa(consumo_min=20, consumo_max=None, valor_m3=8.90, percentual_esgoto=80, ativo=True),
    ])
    db.commit()
    print("✅ Tarifas de teste cadastradas (0-10m³: R$3,50 | 10-20m³: R$5,80 | 20+m³: R$8,90 | esgoto: 80%).")
else:
    print("→ Já existem tarifas cadastradas, não mexi nelas.")
db.close()

print("\nMigração concluída — nenhum dado foi apagado.")

# --- Criptografia do CPF/CNPJ ---
print("\nVerificando criptografia do campo 'documento' (CPF/CNPJ)...")
from criptografia import criptografar, descriptografar

with engine.connect() as conn:
    if EH_POSTGRES:
        # Amplia a coluna — texto cifrado é bem mais longo que um CPF puro.
        # (SQLite não precisa disso: lá TEXT/VARCHAR não tem limite de tamanho real.)
        conn.execute(text("ALTER TABLE clientes ALTER COLUMN documento TYPE VARCHAR(255)"))
        conn.commit()

    linhas = conn.execute(text("SELECT id, documento FROM clientes WHERE documento IS NOT NULL")).fetchall()
    migrados = 0
    for id_cliente, valor_atual in linhas:
        try:
            descriptografar(valor_atual)
            # Se conseguiu descriptografar, já está migrado — não mexe de novo.
        except Exception:
            # Ainda é texto puro (CPF de verdade) — criptografa agora.
            valor_cifrado = criptografar(valor_atual)
            conn.execute(
                text("UPDATE clientes SET documento = :novo WHERE id = :id"),
                {"novo": valor_cifrado, "id": id_cliente},
            )
            migrados += 1
    conn.commit()

    if migrados:
        print(f"✅ {migrados} CPF/CNPJ criptografado(s) agora (AES-256).")
    else:
        print("→ Nenhum CPF pendente de criptografia (ou não havia nenhum salvo ainda).")
