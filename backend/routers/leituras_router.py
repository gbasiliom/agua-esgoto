import os
import uuid
import hashlib
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth

router = APIRouter(prefix="/leituras", tags=["leituras"])

PASTA_FOTOS = os.getenv("PASTA_FOTOS_LEITURAS", "uploads/leituras")
os.makedirs(PASTA_FOTOS, exist_ok=True)


def _competencia_atual():
    agora = datetime.utcnow()
    return f"{agora.year:04d}-{agora.month:02d}"


def _tentar_ocr(caminho_foto: str):
    """
    Melhor esforço: tenta ler os dígitos da foto com Tesseract, se estiver
    instalado. Se não estiver (ou falhar por qualquer motivo), simplesmente
    não faz a checagem automática — a validação de verdade é sempre manual,
    no painel. Nunca trava o envio da leitura por causa disso.
    """
    try:
        import pytesseract
        from PIL import Image

        imagem = Image.open(caminho_foto)
        texto = pytesseract.image_to_string(imagem, config="--psm 7 -c tessedit_char_whitelist=0123456789")
        digitos = re.sub(r"\D", "", texto)
        if digitos:
            return float(digitos)
    except Exception:
        pass
    return None


@router.post("/", response_model=schemas.LeituraOut)
async def enviar_leitura(
    valor_informado: float = Form(...),
    foto: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    """Cliente envia a leitura do mês: número digitado + foto do hidrômetro."""
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        raise HTTPException(status_code=400, detail="Complete seu cadastro antes de enviar uma leitura")
    if not schemas.localidade_tem_hidrometro(cliente.localidade):
        raise HTTPException(status_code=400, detail="Leitura de hidrômetro só existe na sede. Sua localidade não tem hidrômetro.")

    competencia = _competencia_atual()
    ja_existe = db.query(models.LeituraHidrometro).filter(
        models.LeituraHidrometro.cliente_id == cliente.id,
        models.LeituraHidrometro.competencia == competencia,
    ).first()
    if ja_existe:
        raise HTTPException(status_code=400, detail=f"Você já enviou a leitura de {competencia} este mês")

    conteudo = await foto.read()
    hash_foto = hashlib.sha256(conteudo).hexdigest()

    # Anti-fraude: essa exata foto (mesmo arquivo) já foi usada em qualquer
    # leitura antes? Impede reaproveitar uma foto antiga/de outro mês.
    foto_repetida = db.query(models.LeituraHidrometro).filter(
        models.LeituraHidrometro.foto_hash == hash_foto
    ).first()
    if foto_repetida:
        raise HTTPException(
            status_code=400,
            detail="Esta foto já foi usada em outra leitura. Tire uma foto nova do hidrômetro agora.",
        )

    extensao = os.path.splitext(foto.filename)[1] or ".jpg"
    nome_arquivo = f"{uuid.uuid4().hex}{extensao}"
    caminho = os.path.join(PASTA_FOTOS, nome_arquivo)
    with open(caminho, "wb") as f:
        f.write(conteudo)

    valor_ocr = _tentar_ocr(caminho)
    ocr_confere = None
    if valor_ocr is not None:
        ocr_confere = abs(valor_ocr - valor_informado) < 1  # tolerância de arredondamento

    leitura = models.LeituraHidrometro(
        cliente_id=cliente.id,
        competencia=competencia,
        valor_informado=valor_informado,
        foto_caminho=caminho,
        foto_hash=hash_foto,
        valor_ocr=valor_ocr,
        ocr_confere=ocr_confere,
        status="pendente",
    )
    db.add(leitura)
    db.commit()
    db.refresh(leitura)
    return leitura


@router.get("/minhas", response_model=List[schemas.LeituraOut])
def minhas_leituras(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        return []
    return (
        db.query(models.LeituraHidrometro)
        .filter(models.LeituraHidrometro.cliente_id == cliente.id)
        .order_by(models.LeituraHidrometro.criado_em.desc())
        .all()
    )


@router.get("/pendente-mes")
def pendente_mes(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    """Diz pro app do cliente se a leitura deste mês já foi enviada ou não (pra mostrar o alerta)."""
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        return {"enviada": False, "status": None, "competencia": _competencia_atual(), "aplica": True}
    if not schemas.localidade_tem_hidrometro(cliente.localidade):
        return {"enviada": False, "status": None, "competencia": _competencia_atual(), "aplica": False}

    competencia = _competencia_atual()
    leitura = db.query(models.LeituraHidrometro).filter(
        models.LeituraHidrometro.cliente_id == cliente.id,
        models.LeituraHidrometro.competencia == competencia,
    ).first()
    return {
        "enviada": leitura is not None,
        "status": leitura.status if leitura else None,
        "competencia": competencia,
        "aplica": True,
    }


@router.get("/ultima")
def ultima_leitura(
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("cliente")),
):
    """Retorna a última leitura aprovada do cliente, pra mostrar como referência na tela de nova leitura."""
    cliente = db.query(models.Cliente).filter(models.Cliente.usuario_id == usuario.id).first()
    if not cliente:
        return {"valor": None, "competencia": None}

    leitura = (
        db.query(models.LeituraHidrometro)
        .filter(models.LeituraHidrometro.cliente_id == cliente.id, models.LeituraHidrometro.status == "aprovada")
        .order_by(models.LeituraHidrometro.criado_em.desc())
        .first()
    )
    if not leitura:
        return {"valor": None, "competencia": None}
    return {"valor": float(leitura.valor_informado), "competencia": leitura.competencia}


@router.get("/", response_model=List[schemas.LeituraOut])
def listar_leituras(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    query = db.query(models.LeituraHidrometro)
    if status:
        query = query.filter(models.LeituraHidrometro.status == status)
    return query.order_by(models.LeituraHidrometro.criado_em.desc()).all()


@router.patch("/{leitura_id}/aprovar", response_model=schemas.LeituraOut)
def aprovar_leitura(
    leitura_id: int,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    leitura = db.query(models.LeituraHidrometro).filter(models.LeituraHidrometro.id == leitura_id).first()
    if not leitura:
        raise HTTPException(status_code=404, detail="Leitura não encontrada")
    leitura.status = "aprovada"
    leitura.validado_em = datetime.utcnow()
    leitura.validado_por = usuario.id
    db.commit()
    db.refresh(leitura)

    # Aprovou a leitura → gera a fatura na hora, sozinho.
    from routers.faturamento_router import gerar_fatura_da_leitura
    gerar_fatura_da_leitura(db, leitura)

    return leitura


@router.patch("/{leitura_id}/rejeitar", response_model=schemas.LeituraOut)
def rejeitar_leitura(
    leitura_id: int,
    dados: schemas.RejeitarLeitura,
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "operador")),
):
    leitura = db.query(models.LeituraHidrometro).filter(models.LeituraHidrometro.id == leitura_id).first()
    if not leitura:
        raise HTTPException(status_code=404, detail="Leitura não encontrada")
    leitura.status = "rejeitada"
    leitura.observacao = dados.observacao
    leitura.validado_em = datetime.utcnow()
    leitura.validado_por = usuario.id
    db.commit()
    db.refresh(leitura)
    return leitura
