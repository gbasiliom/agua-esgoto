import os
import uuid
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/estoque", tags=["estoque"])

LOCALIZACAO_TIPOS = ("sede", "unidade", "tecnico")


def _obter_ou_criar_saldo(db: Session, item_id: int, localizacao_tipo: str, localizacao_valor: str):
    saldo = db.query(models.EstoqueSaldo).filter(
        models.EstoqueSaldo.item_id == item_id,
        models.EstoqueSaldo.localizacao_tipo == localizacao_tipo,
        models.EstoqueSaldo.localizacao_valor == localizacao_valor,
    ).first()
    if not saldo:
        saldo = models.EstoqueSaldo(
            item_id=item_id, localizacao_tipo=localizacao_tipo,
            localizacao_valor=localizacao_valor, quantidade=0,
        )
        db.add(saldo)
        db.flush()
    return saldo


def aplicar_movimentacao(db: Session, item_id: int, tipo: str, quantidade: float,
                          origem_tipo: Optional[str], origem_valor: Optional[str],
                          destino_tipo: Optional[str], destino_valor: Optional[str],
                          usuario_id: int, chamado_id: Optional[int] = None,
                          observacao: Optional[str] = None):
    """
    Núcleo do livro-razão: debita da origem (se houver) e credita no destino
    (se houver). Uma 'entrada' só credita (compra externa). Uma 'baixa_os' ou
    'saida' só debita (consumo final). Uma 'transferencia' faz as duas coisas
    — o total do sistema nunca muda, só troca de lugar.
    """
    if origem_tipo and origem_valor:
        saldo_origem = _obter_ou_criar_saldo(db, item_id, origem_tipo, origem_valor)
        saldo_origem.quantidade = float(saldo_origem.quantidade) - quantidade
        # Não bloqueia saldo negativo de propósito — ver observação sobre
        # técnicos offline no README. O negativo é o sinal de alerta, não um erro.

    if destino_tipo and destino_valor:
        saldo_destino = _obter_ou_criar_saldo(db, item_id, destino_tipo, destino_valor)
        saldo_destino.quantidade = float(saldo_destino.quantidade) + quantidade

    movimentacao = models.EstoqueMovimentacao(
        item_id=item_id, tipo=tipo, quantidade=quantidade,
        origem_tipo=origem_tipo, origem_valor=origem_valor,
        destino_tipo=destino_tipo, destino_valor=destino_valor,
        chamado_id=chamado_id, usuario_id=usuario_id, observacao=observacao,
    )
    db.add(movimentacao)
    return movimentacao


def _ler_saldo(db: Session, item_id: int, localizacao_tipo: str, localizacao_valor: str) -> float:
    saldo = db.query(models.EstoqueSaldo).filter(
        models.EstoqueSaldo.item_id == item_id,
        models.EstoqueSaldo.localizacao_tipo == localizacao_tipo,
        models.EstoqueSaldo.localizacao_valor == localizacao_valor,
    ).first()
    return float(saldo.quantidade) if saldo else 0.0


def debitar_com_fallback_unidade(db: Session, item_id: int, quantidade: float, tecnico_id: int,
                                  localidade: str, usuario_id: int, chamado_id: Optional[int] = None,
                                  observacao: Optional[str] = None):
    """
    Baixa de material que o técnico usou: debita primeiro do que ele tem
    individualmente; se não for suficiente, completa debitando do estoque
    compartilhado da unidade dele. Assim, uma transferência sede→unidade já
    basta pro técnico usar — não precisa do passo extra unidade→técnico.
    """
    saldo_individual = _ler_saldo(db, item_id, "tecnico", str(tecnico_id))

    if saldo_individual >= quantidade:
        aplicar_movimentacao(
            db, item_id, "baixa_os", quantidade,
            origem_tipo="tecnico", origem_valor=str(tecnico_id),
            destino_tipo=None, destino_valor=None,
            usuario_id=usuario_id, chamado_id=chamado_id, observacao=observacao,
        )
        return

    if saldo_individual > 0:
        aplicar_movimentacao(
            db, item_id, "baixa_os", saldo_individual,
            origem_tipo="tecnico", origem_valor=str(tecnico_id),
            destino_tipo=None, destino_valor=None,
            usuario_id=usuario_id, chamado_id=chamado_id, observacao=observacao,
        )

    restante = quantidade - saldo_individual
    if restante > 0:
        aplicar_movimentacao(
            db, item_id, "baixa_os", restante,
            origem_tipo="unidade", origem_valor=localidade,
            destino_tipo=None, destino_valor=None,
            usuario_id=usuario_id, chamado_id=chamado_id,
            observacao=(observacao or "") + " (completado do estoque da unidade)",
        )


@router.post("/itens", response_model=schemas.EstoqueItemOut)
def criar_item(
    dados: schemas.EstoqueItemCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    item = models.EstoqueItem(**dados.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return _com_saldo(db, item)


@router.get("/itens", response_model=List[schemas.EstoqueItemOut])
def listar_itens(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_equipe()),
):
    itens = db.query(models.EstoqueItem).filter(models.EstoqueItem.ativo == True).all()
    return [_com_saldo(db, item) for item in itens]


@router.patch("/itens/{item_id}", response_model=schemas.EstoqueItemOut)
def atualizar_item(
    item_id: int,
    dados: schemas.EstoqueItemCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    item = db.query(models.EstoqueItem).filter(models.EstoqueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    for campo, valor in dados.model_dump().items():
        setattr(item, campo, valor)
    db.commit()
    db.refresh(item)
    return _com_saldo(db, item)


@router.patch("/itens/{item_id}/desativar", response_model=schemas.EstoqueItemOut)
def desativar_item(
    item_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Some da lista ativa, mas o histórico de movimentações continua intacto."""
    item = db.query(models.EstoqueItem).filter(models.EstoqueItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")
    item.ativo = False
    db.commit()
    db.refresh(item)
    return _com_saldo(db, item)


def _com_saldo(db: Session, item: models.EstoqueItem):
    saldo_total = db.query(func.coalesce(func.sum(models.EstoqueSaldo.quantidade), 0)).filter(
        models.EstoqueSaldo.item_id == item.id
    ).scalar()
    item_out = schemas.EstoqueItemOut.model_validate(item)
    item_out.saldo_total = float(saldo_total)
    item_out.valor_total = float(saldo_total) * float(item.valor_unitario)
    return item_out


@router.get("/alerta-minimo", response_model=List[schemas.EstoqueItemOut])
def itens_abaixo_do_minimo(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Itens cujo saldo total (somado em todas as localizações) está abaixo do mínimo cadastrado."""
    itens = db.query(models.EstoqueItem).filter(models.EstoqueItem.ativo == True).all()
    resultado = []
    for item in itens:
        item_out = _com_saldo(db, item)
        if item_out.saldo_total < float(item.estoque_minimo):
            resultado.append(item_out)
    return resultado


@router.get("/meu-estoque-completo", response_model=List[schemas.SaldoOut])
def meu_estoque_completo(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico")),
):
    """
    O que o técnico vê como 'meu estoque': soma do que é só dele (transferido
    direto pra ele) + o que é compartilhado da unidade dele (transferido
    sede→unidade, sem precisar do passo extra unidade→técnico).
    """
    localidade = usuario.localidade or "sede"

    saldos_individuais = db.query(models.EstoqueSaldo, models.EstoqueItem).join(
        models.EstoqueItem, models.EstoqueSaldo.item_id == models.EstoqueItem.id
    ).filter(
        models.EstoqueSaldo.localizacao_tipo == "tecnico",
        models.EstoqueSaldo.localizacao_valor == str(usuario.id),
    ).all()

    saldos_unidade = db.query(models.EstoqueSaldo, models.EstoqueItem).join(
        models.EstoqueItem, models.EstoqueSaldo.item_id == models.EstoqueItem.id
    ).filter(
        models.EstoqueSaldo.localizacao_tipo == "unidade",
        models.EstoqueSaldo.localizacao_valor == localidade,
    ).all()

    combinado = {}  # item_id -> {nome_item, unidade_medida, quantidade}
    for saldo, item in saldos_individuais:
        combinado[item.id] = {
            "nome_item": item.nome, "unidade_medida": item.unidade_medida,
            "quantidade": float(saldo.quantidade),
        }
    for saldo, item in saldos_unidade:
        if item.id in combinado:
            combinado[item.id]["quantidade"] += float(saldo.quantidade)
        else:
            combinado[item.id] = {
                "nome_item": item.nome, "unidade_medida": item.unidade_medida,
                "quantidade": float(saldo.quantidade),
            }

    return [
        schemas.SaldoOut(
            item_id=item_id, nome_item=dados["nome_item"], unidade_medida=dados["unidade_medida"],
            localizacao_tipo="tecnico+unidade", localizacao_valor=localidade, quantidade=dados["quantidade"],
        )
        for item_id, dados in combinado.items()
        if dados["quantidade"] != 0
    ]


@router.get("/saldo", response_model=List[schemas.SaldoOut])
def consultar_saldo(
    localizacao_tipo: Optional[str] = None,
    localizacao_valor: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_equipe()),
):
    """
    Consulta o saldo. Sem filtros, retorna tudo (uso do painel). Com
    localizacao_tipo=tecnico e localizacao_valor=<id>, retorna só o que
    aquele técnico tem em mãos (uso do app técnico).
    """
    query = db.query(models.EstoqueSaldo, models.EstoqueItem).join(
        models.EstoqueItem, models.EstoqueSaldo.item_id == models.EstoqueItem.id
    )
    if localizacao_tipo:
        query = query.filter(models.EstoqueSaldo.localizacao_tipo == localizacao_tipo)
    if localizacao_valor:
        query = query.filter(models.EstoqueSaldo.localizacao_valor == localizacao_valor)

    resultado = []
    for saldo, item in query.all():
        if float(saldo.quantidade) == 0:
            continue  # não polui a lista com zerados
        resultado.append(schemas.SaldoOut(
            item_id=item.id, nome_item=item.nome, unidade_medida=item.unidade_medida,
            localizacao_tipo=saldo.localizacao_tipo, localizacao_valor=saldo.localizacao_valor,
            quantidade=float(saldo.quantidade),
        ))
    return resultado


@router.post("/solicitacoes", response_model=schemas.SolicitacaoOut)
def solicitar_material(
    dados: schemas.SolicitacaoCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico")),
):
    """Técnico pede material (reparo ou insumo de ETA) — fica pendente até o operador aprovar."""
    solicitacao = models.SolicitacaoMaterial(tecnico_id=usuario.id, **dados.model_dump())
    db.add(solicitacao)
    db.commit()
    db.refresh(solicitacao)
    return solicitacao


@router.get("/solicitacoes", response_model=List[schemas.SolicitacaoOut])
def listar_solicitacoes(
    status: Optional[str] = None,
    minhas: bool = False,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_equipe()),
):
    """
    - Painel Windows (admin/operador): vê todas, filtra por status (ex: pendente).
    - App técnico: chama com minhas=true pra ver só as próprias solicitações.
    """
    query = db.query(models.SolicitacaoMaterial)
    if usuario.tipo not in ("admin", "operador"):
        minhas = True  # técnico só vê as próprias solicitações
    if minhas:
        query = query.filter(models.SolicitacaoMaterial.tecnico_id == usuario.id)
    if status:
        query = query.filter(models.SolicitacaoMaterial.status == status)
    return query.order_by(models.SolicitacaoMaterial.criado_em.desc()).all()


@router.patch("/solicitacoes/{solicitacao_id}/aprovar", response_model=schemas.SolicitacaoOut)
def aprovar_solicitacao(
    solicitacao_id: int,
    modo: str = "estoque",  # "estoque" (transfere da sede) ou "compra_direta" (autoriza comprar com fornecedor)
    origem_tipo: str = "sede",
    origem_valor: str = "sede",
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """
    Aprova a solicitação de dois jeitos possíveis:
    - modo="estoque": transfere o material da sede pra ETA (unidade) do técnico —
      já que o técnico É a ETA, o destino é a unidade dele, não ele individualmente.
    - modo="compra_direta": não mexe em estoque nenhum — só autoriza o técnico a
      comprar direto com um fornecedor. Ele envia o comprovante depois
      (POST /solicitacoes/{id}/comprovante), que já gera a conta a pagar.
    """
    solicitacao = db.query(models.SolicitacaoMaterial).filter(models.SolicitacaoMaterial.id == solicitacao_id).first()
    if not solicitacao:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if solicitacao.status != "pendente":
        raise HTTPException(status_code=400, detail="Esta solicitação já foi respondida")

    if modo == "estoque":
        tecnico = db.query(models.Usuario).filter(models.Usuario.id == solicitacao.tecnico_id).first()
        localidade_tecnico = (tecnico.localidade if tecnico else None) or "sede"
        aplicar_movimentacao(
            db, solicitacao.item_id, "transferencia", float(solicitacao.quantidade),
            origem_tipo, origem_valor, "unidade", localidade_tecnico,
            usuario_id=usuario.id, chamado_id=solicitacao.chamado_id,
            observacao=f"Aprovação da solicitação #{solicitacao.id}",
        )
    elif modo == "compra_direta":
        pass  # nenhuma movimentação de estoque ainda — só libera o técnico pra comprar
    else:
        raise HTTPException(status_code=400, detail="modo precisa ser 'estoque' ou 'compra_direta'")

    solicitacao.status = "aprovada"
    solicitacao.modo_aprovacao = modo
    solicitacao.respondida_em = datetime.utcnow()
    db.commit()
    db.refresh(solicitacao)
    return solicitacao


@router.patch("/solicitacoes/{solicitacao_id}/negar", response_model=schemas.SolicitacaoOut)
def negar_solicitacao(
    solicitacao_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    solicitacao = db.query(models.SolicitacaoMaterial).filter(models.SolicitacaoMaterial.id == solicitacao_id).first()
    if not solicitacao:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if solicitacao.status != "pendente":
        raise HTTPException(status_code=400, detail="Esta solicitação já foi respondida")

    solicitacao.status = "negada"
    solicitacao.respondida_em = datetime.utcnow()
    db.commit()
    db.refresh(solicitacao)
    return solicitacao


@router.post("/solicitacoes/{solicitacao_id}/comprovante", response_model=schemas.SolicitacaoOut)
async def enviar_comprovante_compra(
    solicitacao_id: int,
    fornecedor_id: int = Form(...),
    valor_compra: float = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico")),
):
    """
    Técnico envia a prova da compra direta autorizada: fornecedor onde
    comprou, valor da nota, e a foto da nota fiscal. Isso já gera a conta a
    pagar pro fornecedor automaticamente.
    """
    solicitacao = db.query(models.SolicitacaoMaterial).filter(models.SolicitacaoMaterial.id == solicitacao_id).first()
    if not solicitacao:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
    if solicitacao.tecnico_id != usuario.id:
        raise HTTPException(status_code=403, detail="Esta solicitação não é sua")
    if solicitacao.status != "aprovada" or solicitacao.modo_aprovacao != "compra_direta":
        raise HTTPException(status_code=400, detail="Esta solicitação não está autorizada pra compra direta")
    if solicitacao.nota_fiscal_foto:
        raise HTTPException(status_code=400, detail="Comprovante já foi enviado pra essa solicitação")

    fornecedor = db.query(models.Fornecedor).filter(models.Fornecedor.id == fornecedor_id).first()
    if not fornecedor:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado — cadastre ele primeiro no painel")

    conteudo = await foto.read()
    extensao = os.path.splitext(foto.filename)[1] or ".jpg"
    nome_arquivo = f"nota_fiscal_{uuid.uuid4().hex}{extensao}"
    pasta = "uploads/notas_fiscais"
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome_arquivo)
    with open(caminho, "wb") as f:
        f.write(conteudo)

    solicitacao.fornecedor_id = fornecedor_id
    solicitacao.valor_compra = valor_compra
    solicitacao.nota_fiscal_foto = caminho
    solicitacao.nota_fiscal_enviada_em = datetime.utcnow()
    db.commit()

    # Gera a conta a pagar pro fornecedor automaticamente
    item = db.query(models.EstoqueItem).filter(models.EstoqueItem.id == solicitacao.item_id).first()
    nome_item = item.nome if item else "material"
    conta = models.ContaPagar(
        fornecedor_id=fornecedor_id,
        descricao=f"Compra direta autorizada — {nome_item} (solicitação #{solicitacao.id})",
        valor=valor_compra,
        vencimento=datetime.utcnow(),
        status="aberto",
    )
    db.add(conta)
    db.commit()
    db.refresh(solicitacao)
    return solicitacao


# --- Manutenção da ETA ---

@router.post("/manutencao-eta", response_model=schemas.ManutencaoEtaOut)
def registrar_manutencao_eta(
    dados: schemas.ManutencaoEtaCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico")),
):
    """Técnico registra uma manutenção feita na ETA da própria localidade (limpeza de tanque, verificação de cloro etc)."""
    manutencao = models.ManutencaoEta(
        tecnico_id=usuario.id,
        localidade=usuario.localidade or "sede",
        tipo=dados.tipo,
        descricao=dados.descricao,
    )
    db.add(manutencao)
    db.commit()
    db.refresh(manutencao)
    return manutencao


@router.get("/manutencao-eta", response_model=List[schemas.ManutencaoEtaOut])
def listar_manutencoes_eta(
    localidade: Optional[str] = None,
    minhas: bool = False,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_equipe()),
):
    """
    - Painel Windows (admin/operador): vê tudo, filtra por localidade.
    - App técnico: chama com minhas=true pra ver só o próprio histórico.
    """
    query = db.query(models.ManutencaoEta)
    if usuario.tipo not in ("admin", "operador"):
        minhas = True  # técnico só vê o próprio histórico
    if minhas:
        query = query.filter(models.ManutencaoEta.tecnico_id == usuario.id)
    if localidade:
        query = query.filter(models.ManutencaoEta.localidade == localidade)
    return query.order_by(models.ManutencaoEta.criado_em.desc()).all()


@router.post("/movimentar", response_model=schemas.SaldoOut)
def movimentar(
    dados: schemas.MovimentacaoCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """
    Registra uma movimentação manual: entrada (compra, só destino), saída
    (baixa manual, só origem), transferência (sede→unidade ou unidade→técnico,
    origem e destino) ou ajuste (correção de contagem física).
    """
    item = db.query(models.EstoqueItem).filter(models.EstoqueItem.id == dados.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item de estoque não encontrado")

    if dados.tipo == "entrada" and not dados.destino_tipo:
        raise HTTPException(status_code=400, detail="Entrada precisa de um destino (pra onde o material vai)")
    if dados.tipo == "saida" and not dados.origem_tipo:
        raise HTTPException(status_code=400, detail="Saída precisa de uma origem (de onde o material sai)")
    if dados.tipo == "transferencia" and not (dados.origem_tipo and dados.destino_tipo):
        raise HTTPException(status_code=400, detail="Transferência precisa de origem e destino")

    aplicar_movimentacao(
        db, item.id, dados.tipo, dados.quantidade,
        dados.origem_tipo, dados.origem_valor, dados.destino_tipo, dados.destino_valor,
        usuario_id=usuario.id, observacao=dados.observacao,
    )
    db.commit()

    localizacao_tipo_consulta = dados.destino_tipo or dados.origem_tipo
    localizacao_valor_consulta = dados.destino_valor or dados.origem_valor
    saldo = db.query(models.EstoqueSaldo).filter(
        models.EstoqueSaldo.item_id == item.id,
        models.EstoqueSaldo.localizacao_tipo == localizacao_tipo_consulta,
        models.EstoqueSaldo.localizacao_valor == localizacao_valor_consulta,
    ).first()
    return schemas.SaldoOut(
        item_id=item.id, nome_item=item.nome, unidade_medida=item.unidade_medida,
        localizacao_tipo=localizacao_tipo_consulta, localizacao_valor=localizacao_valor_consulta,
        quantidade=float(saldo.quantidade) if saldo else 0,
    )
