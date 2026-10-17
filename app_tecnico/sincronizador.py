"""
Roda a fila de ações feitas offline (iniciar/fechar chamado) contra a API
de verdade. Para no primeiro erro (provavelmente ainda sem internet) e
deixa o resto na fila pra tentar de novo depois.
"""
import armazenamento_local as db_local


def sincronizar(pasta_dados, api):
    """Retorna (quantidade_sincronizada, ainda_restando_na_fila)."""
    fila = db_local.listar_fila(pasta_dados)
    sincronizados = 0

    for item in fila:
        try:
            if item["tipo_acao"] == "iniciar":
                api.iniciar_atendimento(item["chamado_id"])
            elif item["tipo_acao"] == "fechar":
                payload = item["payload"]
                api.fechar_chamado(
                    item["chamado_id"],
                    payload["descricao_solucao"],
                    payload["fotos"],
                    checklist=payload.get("checklist"),
                    materiais=payload.get("materiais_utilizados"),
                    itens_estoque_usados=payload.get("itens_estoque_usados"),
                )
        except Exception:
            # Provavelmente ainda sem internet — para por aqui e tenta de
            # novo na próxima vez (não descarta a ação).
            break

        db_local.remover_da_fila(pasta_dados, item["id"])
        sincronizados += 1

    restando = db_local.contar_pendentes(pasta_dados)
    return sincronizados, restando
