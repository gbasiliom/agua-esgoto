"""Fila offline em SQLite: lançamentos feitos sem sinal, enviados depois, em ordem."""
import json
import os
import sqlite3
from datetime import datetime


def _conn(pasta):
    os.makedirs(pasta, exist_ok=True)
    c = sqlite3.connect(os.path.join(pasta, "fila.db"))
    c.execute("""CREATE TABLE IF NOT EXISTS fila (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, payload TEXT NOT NULL, criado_em TEXT NOT NULL)""")
    c.commit()
    return c


def enfileirar(pasta, tipo, payload):
    c = _conn(pasta)
    c.execute("INSERT INTO fila (tipo, payload, criado_em) VALUES (?,?,?)",
              (tipo, json.dumps(payload, ensure_ascii=False), datetime.now().isoformat()))
    c.commit(); c.close()


def listar(pasta):
    c = _conn(pasta)
    linhas = c.execute("SELECT id, tipo, payload, criado_em FROM fila ORDER BY id").fetchall()
    c.close()
    return [{"id": i, "tipo": t, "payload": json.loads(p), "criado_em": ce} for i, t, p, ce in linhas]


def remover(pasta, item_id):
    c = _conn(pasta)
    c.execute("DELETE FROM fila WHERE id=?", (item_id,))
    c.commit(); c.close()


def contar(pasta):
    c = _conn(pasta)
    n = c.execute("SELECT COUNT(*) FROM fila").fetchone()[0]
    c.close()
    return n


def rejeitar(pasta, item, motivo):
    """Move para a tabela de rejeitados (nunca descarta dado em silêncio)."""
    c = _conn(pasta)
    c.execute("""CREATE TABLE IF NOT EXISTS rejeitados (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, payload TEXT, criado_em TEXT, motivo TEXT)""")
    c.execute("INSERT INTO rejeitados (tipo, payload, criado_em, motivo) VALUES (?,?,?,?)",
              (item["tipo"], json.dumps(item["payload"], ensure_ascii=False), item["criado_em"], motivo))
    c.execute("DELETE FROM fila WHERE id=?", (item["id"],))
    c.commit(); c.close()


def listar_rejeitados(pasta):
    c = _conn(pasta)
    c.execute("""CREATE TABLE IF NOT EXISTS rejeitados (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, payload TEXT, criado_em TEXT, motivo TEXT)""")
    linhas = c.execute("SELECT id, tipo, payload, criado_em, motivo FROM rejeitados ORDER BY id").fetchall()
    c.close()
    return [{"id": i, "tipo": t, "payload": json.loads(p), "criado_em": ce, "motivo": m} for i, t, p, ce, m in linhas]


def sincronizar(pasta, enviar):
    """`enviar(tipo, payload)` levanta exceção se falhar.
    - Sem conexão ou sessão expirada: PARA e mantém tudo na fila.
    - Servidor recusou o item (dado inválido): vai para `rejeitados` (o app avisa o usuário) e segue.
    Retorna (enviados, rejeitados_agora, restantes)."""
    from api_base import ErroConexao, ErroSessao, ApiError
    enviados, rej = 0, 0
    for item in listar(pasta):
        try:
            enviar(item["tipo"], item["payload"])
        except (ErroConexao, ErroSessao):
            break
        except ApiError as e:
            rejeitar(pasta, item, str(e))
            rej += 1
            continue
        remover(pasta, item["id"])
        enviados += 1
    return enviados, rej, contar(pasta)
