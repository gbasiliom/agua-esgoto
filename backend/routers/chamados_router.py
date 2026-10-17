import os
import uuid
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/chamados", tags=["chamados"])

PASTA_FOTOS = os.getenv("PASTA_FOTOS", "uploads/chamados")
os.makedirs(PASTA_FOTOS, exist_ok=True)


@router.post("/meu", response_model=schemas.ChamadoOut)
def abrir_meu_chamado(
    dados: schemas.ChamadoCreateCliente,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    """O cliente abre um chamado pelo app — o cliente_id é descoberto automaticamente pelo login dele."""
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        raise HTTPException(status_code=400, detail="Complete seu cadastro antes de abrir um chamado (POST /clientes/eu)")
    if cliente.status_cadastro == "pendente":
        raise HTTPException(status_code=403, detail="Seu cadastro ainda está aguardando aprovação do operador.")

    chamado = models.Chamado(cliente_id=cliente.id, local_atendimento=cliente.localidade, **dados.model_dump())
    db.add(chamado)
    db.commit()
    db.refresh(chamado)
    return chamado


@router.get("/meus", response_model=List[schemas.ChamadoOut])
def meus_chamados(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    """Lista os chamados do próprio cliente logado."""
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        return []
    return (
        db.query(models.Chamado)
        .filter(models.Chamado.cliente_id == cliente.id)
        .order_by(models.Chamado.abertura.desc())
        .all()
    )


@router.post("/", response_model=schemas.ChamadoOut)
def abrir_chamado(
    dados: schemas.ChamadoCreate,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Operador (via telefone/whatsapp) abre um chamado em nome de um cliente. O cliente pelo app usa /chamados/meu."""
    cliente = db.query(models.Cliente).filter(models.Cliente.id == dados.cliente_id).first()
    chamado = models.Chamado(
        local_atendimento=cliente.localidade if cliente else None,
        **dados.model_dump(),
    )
    db.add(chamado)
    db.commit()
    db.refresh(chamado)
    return chamado


@router.patch("/{chamado_id}/local-atendimento", response_model=schemas.ChamadoOut)
def atualizar_local_atendimento(
    chamado_id: int,
    localidade: str,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Permite o operador corrigir manualmente a unidade responsável pelo chamado."""
    chamado = db.query(models.Chamado).filter(models.Chamado.id == chamado_id).first()
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")
    chamado.local_atendimento = localidade
    db.commit()
    db.refresh(chamado)
    return chamado


@router.get("/", response_model=List[schemas.ChamadoOut])
def listar_chamados(
    status: Optional[str] = None,
    tecnico_id: Optional[int] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.usuario_atual),
):
    """
    - Painel Windows: lista tudo (filtra por status se quiser).
    - App do técnico: chama com tecnico_id=<seu id> pra ver só os dele.
    """
    if usuario.tipo == "cliente":
        raise HTTPException(status_code=403, detail="Sem permissão para esta ação")
    query = db.query(models.Chamado)
    if usuario.tipo == "tecnico":
        tecnico_id = usuario.id  # técnico só enxerga os chamados dele, mesmo que peça outro id
    if status:
        query = query.filter(models.Chamado.status == status)
    if tecnico_id:
        query = query.filter(models.Chamado.tecnico_id == tecnico_id)
    return query.order_by(models.Chamado.abertura.desc()).all()


@router.patch("/{chamado_id}/atribuir", response_model=schemas.ChamadoOut)
def atribuir_tecnico(
    chamado_id: int,
    dados: schemas.ChamadoAtribuir,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """Só o painel Windows (admin/operador) atribui técnico a um chamado."""
    chamado = db.query(models.Chamado).filter(models.Chamado.id == chamado_id).first()
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    chamado.tecnico_id = dados.tecnico_id
    chamado.status = "atribuido"
    chamado.atribuicao = datetime.utcnow()
    db.commit()
    db.refresh(chamado)
    return chamado


@router.patch("/{chamado_id}/iniciar", response_model=schemas.ChamadoOut)
def iniciar_atendimento(
    chamado_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico")),
):
    """Técnico marca que chegou no local e começou o atendimento (app Android)."""
    chamado = db.query(models.Chamado).filter(models.Chamado.id == chamado_id).first()
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")
    if chamado.tecnico_id != usuario.id:
        raise HTTPException(status_code=403, detail="Este chamado não está atribuído a você")

    chamado.status = "em_andamento"
    db.commit()
    db.refresh(chamado)
    return chamado


@router.post("/{chamado_id}/fechar", response_model=schemas.ChamadoOut)
def fechar_chamado(
    chamado_id: int,
    descricao_solucao: str = Form(...),
    checklist: Optional[str] = Form(None),
    materiais_utilizados: Optional[str] = Form(None),
    itens_estoque_usados: Optional[str] = Form(None),  # JSON: [{"item_id": 1, "quantidade": 2}, ...]
    fotos: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("tecnico")),
):
    """
    Técnico fecha o chamado pelo app Android: descrição do que foi feito
    + checklist da situação encontrada + materiais usados (texto livre)
    + itens de estoque vinculados (baixa automática do saldo do técnico)
    + pelo menos 1 foto (obrigatória, tirada na hora).
    """
    chamado = db.query(models.Chamado).filter(models.Chamado.id == chamado_id).first()
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")
    if chamado.tecnico_id != usuario.id:
        raise HTTPException(status_code=403, detail="Este chamado não está atribuído a você")
    if not fotos:
        raise HTTPException(status_code=400, detail="É necessário enviar ao menos 1 foto")

    for foto in fotos:
        extensao = os.path.splitext(foto.filename)[1] or ".jpg"
        nome_arquivo = f"{uuid.uuid4().hex}{extensao}"
        caminho = os.path.join(PASTA_FOTOS, nome_arquivo)
        with open(caminho, "wb") as f:
            f.write(foto.file.read())

        db.add(models.ChamadoFoto(chamado_id=chamado.id, caminho_arquivo=caminho, tipo="fechamento"))

    # Baixa automática: cada item vinculado sai do saldo do próprio técnico
    # e, se não tiver o suficiente, completa do estoque da unidade dele —
    # trigger direto no fechamento, sem passo manual nenhum.
    if itens_estoque_usados:
        try:
            lista_itens = json.loads(itens_estoque_usados)
        except (json.JSONDecodeError, TypeError):
            lista_itens = []

        for item_usado in lista_itens:
            db.add(models.ChamadoMaterialUsado(
                chamado_id=chamado.id, item_id=item_usado["item_id"], quantidade=item_usado["quantidade"],
            ))
            debitar_com_fallback_unidade(
                db, item_usado["item_id"], item_usado["quantidade"], usuario.id,
                usuario.localidade or "sede", usuario_id=usuario.id, chamado_id=chamado.id,
                observacao=f"Baixa automática — fechamento do chamado #{chamado.id}",
            )

    chamado.descricao_solucao = descricao_solucao
    chamado.checklist = checklist
    chamado.materiais_utilizados = materiais_utilizados
    chamado.status = "concluido"
    chamado.conclusao = datetime.utcnow()
    db.commit()
    db.refresh(chamado)
    return chamado


@router.get("/{chamado_id}/fotos")
def listar_fotos(
    chamado_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.usuario_atual),
):
    """Retorna as URLs das fotos de um chamado (pro painel Windows exibir/abrir)."""
    if usuario.tipo in ("cliente", "operador_eta", "quimico"):
        raise HTTPException(status_code=403, detail="Sem permissão para esta ação")
    if usuario.tipo == "tecnico":
        ch = db.query(models.Chamado).filter(models.Chamado.id == chamado_id).first()
        if not ch or ch.tecnico_id != usuario.id:
            raise HTTPException(status_code=403, detail="Sem permissão para este chamado")
    fotos = db.query(models.ChamadoFoto).filter(models.ChamadoFoto.chamado_id == chamado_id).all()
    return [
        {
            "id": f.id,
            "tipo": f.tipo,
            "url": f"/{f.caminho_arquivo}",
            "enviado_em": f.enviado_em,
        }
        for f in fotos
    ]


from fastapi.responses import Response
from pdf_relatorio import gerar_pdf_chamado
from routers.estoque_router import aplicar_movimentacao, debitar_com_fallback_unidade


@router.get("/{chamado_id}/relatorio-pdf")
def relatorio_pdf(
    chamado_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.usuario_atual),
):
    """Gera e devolve o PDF do relatório de atendimento do chamado."""
    chamado = db.query(models.Chamado).filter(models.Chamado.id == chamado_id).first()
    if not chamado:
        raise HTTPException(status_code=404, detail="Chamado não encontrado")

    # Quem pode ver o relatório: a equipe do painel/químico, o técnico daquele chamado e o próprio cliente dono dele.
    if usuario.tipo == "tecnico" and chamado.tecnico_id != usuario.id:
        raise HTTPException(status_code=403, detail="Sem permissão para este chamado")
    if usuario.tipo == "cliente":
        dono = db.query(models.Cliente).filter(models.Cliente.id == chamado.cliente_id, models.Cliente.usuario_id == usuario.id).first()
        if not dono:
            # mesma resposta de "não existe" pra não revelar quais números de chamado existem
            raise HTTPException(status_code=404, detail="Chamado não encontrado")
    if usuario.tipo not in ("admin", "operador", "tecnico", "cliente", "quimico"):
        raise HTTPException(status_code=403, detail="Sem permissão para esta ação")

    cliente = db.query(models.Cliente).filter(models.Cliente.id == chamado.cliente_id).first()
    tecnico = (
        db.query(models.Usuario).filter(models.Usuario.id == chamado.tecnico_id).first()
        if chamado.tecnico_id else None
    )
    fotos = db.query(models.ChamadoFoto).filter(models.ChamadoFoto.chamado_id == chamado.id).all()

    pdf_bytes = gerar_pdf_chamado(chamado, cliente, tecnico, fotos)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=chamado_{chamado_id}.pdf"},
    )


@router.get("/relatorio/resumo")
def relatorio_resumo(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    """KPIs simples pro dashboard do painel Windows."""
    total_abertos = db.query(models.Chamado).filter(models.Chamado.status.in_(["aberto", "atribuido", "em_andamento"])).count()
    total_concluidos = db.query(models.Chamado).filter(models.Chamado.status == "concluido").count()
    por_tipo = {}
    for tipo in ["vazamento", "manutencao", "religacao", "vistoria", "outro"]:
        por_tipo[tipo] = db.query(models.Chamado).filter(models.Chamado.tipo == tipo).count()

    return {
        "chamados_em_aberto": total_abertos,
        "chamados_concluidos": total_concluidos,
        "por_tipo": por_tipo,
    }
