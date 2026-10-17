"""
Armazenamento local no celular do técnico — funciona sem internet.

Duas tabelas:
- chamados_cache: última versão conhecida dos chamados do técnico (pra
  mostrar a lista mesmo sem sinal).
- fila_sincronizacao: ações feitas offline (iniciar/fechar chamado) que
  ainda não foram enviadas pro servidor — processadas assim que o app
  detectar internet de novo.
"""
import os
import sqlite3
import json
from datetime import datetime


def _caminho_banco(pasta_dados):
    return os.path.join(pasta_dados, "offline.db")


def conectar(pasta_dados):
    conn = sqlite3.connect(_caminho_banco(pasta_dados))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chamados_cache (
            id INTEGER PRIMARY KEY,
            dados TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fila_sincronizacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_acao TEXT NOT NULL,
            chamado_id INTEGER NOT NULL,
            payload TEXT NOT NULL,
            criado_em TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def salvar_cache_chamados(pasta_dados, chamados):
    """Sobrescreve o cache local com a lista mais recente vinda do servidor."""
    conn = conectar(pasta_dados)
    conn.execute("DELETE FROM chamados_cache")
    for chamado in chamados:
        conn.execute(
            "INSERT INTO chamados_cache (id, dados) VALUES (?, ?)",
            (chamado["id"], json.dumps(chamado, ensure_ascii=False)),
        )
    conn.commit()
    conn.close()


def carregar_cache_chamados(pasta_dados):
    conn = conectar(pasta_dados)
    linhas = conn.execute("SELECT dados FROM chamados_cache").fetchall()
    conn.close()
    return [json.loads(linha[0]) for linha in linhas]


def atualizar_status_local(pasta_dados, chamado_id, novo_status):
    """Atualiza o status de um chamado só no cache local (otimista, antes de sincronizar)."""
    conn = conectar(pasta_dados)
    linha = conn.execute("SELECT dados FROM chamados_cache WHERE id = ?", (chamado_id,)).fetchone()
    if linha:
        dados = json.loads(linha[0])
        dados["status"] = novo_status
        conn.execute(
            "UPDATE chamados_cache SET dados = ? WHERE id = ?",
            (json.dumps(dados, ensure_ascii=False), chamado_id),
        )
        conn.commit()
    conn.close()


def enfileirar_acao(pasta_dados, tipo_acao, chamado_id, payload: dict):
    """Guarda uma ação (iniciar/fechar) pra enviar pro servidor quando tiver internet."""
    conn = conectar(pasta_dados)
    conn.execute(
        "INSERT INTO fila_sincronizacao (tipo_acao, chamado_id, payload, criado_em) VALUES (?, ?, ?, ?)",
        (tipo_acao, chamado_id, json.dumps(payload, ensure_ascii=False), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def listar_fila(pasta_dados):
    conn = conectar(pasta_dados)
    linhas = conn.execute(
        "SELECT id, tipo_acao, chamado_id, payload, criado_em FROM fila_sincronizacao ORDER BY id"
    ).fetchall()
    conn.close()
    return [
        {"id": linha[0], "tipo_acao": linha[1], "chamado_id": linha[2],
         "payload": json.loads(linha[3]), "criado_em": linha[4]}
        for linha in linhas
    ]


def remover_da_fila(pasta_dados, item_id):
    conn = conectar(pasta_dados)
    conn.execute("DELETE FROM fila_sincronizacao WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def contar_pendentes(pasta_dados):
    conn = conectar(pasta_dados)
    total = conn.execute("SELECT COUNT(*) FROM fila_sincronizacao").fetchone()[0]
    conn.close()
    return total
