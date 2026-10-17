"""
Módulo de Qualidade da Água (setor do químico) — Portaria GM/MS nº 888/2021.

Fluxo: o admin cadastra a configuração de cada sistema (população, manancial,
tipo de filtro) e os pontos de coleta; o sistema gera o plano mínimo de
amostragem; o químico registra coletas, lança resultados do laboratório
próprio (kit/estufa) e anexa os laudos do laboratório externo; positivos geram
recoletas automaticamente; o painel de conformidade compara o que foi feito
com o mínimo exigido.
"""
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from database import get_db
import models
import schemas
import auth
import qualidade_regras as regras_norma

router = APIRouter(prefix="/qualidade", tags=["qualidade-da-agua"])

LEITURA = ("admin", "operador", "quimico")
ESCRITA_LAB = ("admin", "quimico")  # coleta, resultado, laudo
SIGLA_LOCALIDADE = {"sede": "SED", "penha_do_coco": "PDC", "bananal": "BAN", "agua_limpa": "AGL"}
GRUPOS_BACTERIOLOGICOS = ("bact_saida", "bact_rede")
TIPOS_LAUDO = ("agua_bruta_semestral", "bacteriologico", "outro")
EXTENSOES_LAUDO = {".pdf", ".jpg", ".jpeg", ".png"}
TAMANHO_MAX_LAUDO = 15 * 1024 * 1024


def _pasta_persistente():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Pasta PRIVADA (não é montada como arquivo estático): laudos só saem por /qualidade/laudos/{id}/arquivo, com login.
PASTA_LAUDOS = os.path.join(_pasta_persistente(), "dados_laudos")


# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------

def _validar_localidade(localidade: str):
    if localidade not in schemas.LOCALIDADES:
        raise HTTPException(status_code=400, detail=f"Localidade inválida. Use: {', '.join(schemas.LOCALIDADES)}")


def _config_ou_404(db: Session, localidade: str) -> models.ConfigSistemaAgua:
    config = db.query(models.ConfigSistemaAgua).filter(models.ConfigSistemaAgua.localidade == localidade).first()
    if not config:
        raise HTTPException(
            status_code=404,
            detail="Sistema ainda não configurado. Informe população abastecida, manancial e tipo de filtro (PUT /qualidade/config/{localidade}).",
        )
    return config


def _intervalo(ini: date, fim: date):
    return datetime.combine(ini, datetime.min.time()), datetime.combine(fim, datetime.max.time())


def _novo_codigo(amostra: models.Amostra, quando: datetime) -> str:
    sigla = SIGLA_LOCALIDADE.get(amostra.localidade, "XXX")
    return f"{sigla}{quando:%Y%m%d}-{amostra.id:05d}"


def _parse_mes(mes: Optional[str]):
    if not mes:
        hoje = date.today()
        return hoje.year, hoje.month
    try:
        ano, m = mes.split("-")
        ano, m = int(ano), int(m)
        assert 1 <= m <= 12 and 2000 <= ano <= 2100
        return ano, m
    except Exception:
        raise HTTPException(status_code=400, detail="Mês inválido. Use o formato AAAA-MM (ex.: 2026-10).")


def _laudo_out(laudo: models.LaudoExterno) -> schemas.LaudoExternoOut:
    return schemas.LaudoExternoOut(
        id=laudo.id, localidade=laudo.localidade, ponto_id=laudo.ponto_id, amostra_id=laudo.amostra_id,
        tipo=laudo.tipo, laboratorio=laudo.laboratorio, numero_laudo=laudo.numero_laudo,
        data_coleta=laudo.data_coleta, data_emissao=laudo.data_emissao,
        parametros_resumo=laudo.parametros_resumo, conforme=laudo.conforme,
        tem_arquivo=bool(laudo.arquivo), observacoes=laudo.observacoes,
    )


# ----------------------------------------------------------------------------
# Configuração do sistema e plano de amostragem
# ----------------------------------------------------------------------------

@router.get("/config/{localidade}", response_model=schemas.ConfigSistemaAguaOut)
def ver_config(localidade: str, db: Session = Depends(get_db),
               usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    _validar_localidade(localidade)
    return _config_ou_404(db, localidade)


@router.put("/config/{localidade}", response_model=schemas.ConfigSistemaAguaOut)
def salvar_config(localidade: str, dados: schemas.ConfigSistemaAguaIn, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(auth.exigir_tipo("admin"))):
    _validar_localidade(localidade)
    if dados.manancial not in ("superficial", "subterraneo"):
        raise HTTPException(status_code=400, detail="Manancial deve ser 'superficial' ou 'subterraneo'")
    if dados.manancial == "superficial" and dados.filtracao not in ("lenta", "rapida"):
        raise HTTPException(status_code=400, detail="Informe a filtração: 'lenta' ou 'rapida'")
    if dados.populacao_abastecida < 0 or dados.numero_filtros < 1:
        raise HTTPException(status_code=400, detail="População não pode ser negativa e o número de filtros deve ser ao menos 1")

    config = db.query(models.ConfigSistemaAgua).filter(models.ConfigSistemaAgua.localidade == localidade).first()
    if not config:
        config = models.ConfigSistemaAgua(localidade=localidade)
        db.add(config)
    config.populacao_abastecida = dados.populacao_abastecida
    config.manancial = dados.manancial
    config.filtracao = dados.filtracao if dados.manancial == "superficial" else None
    config.numero_filtros = dados.numero_filtros
    db.commit()
    db.refresh(config)
    return config


@router.post("/regras/gerar/{localidade}", response_model=schemas.GerarRegrasOut)
def gerar_regras(localidade: str, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(auth.exigir_tipo("admin"))):
    """(Re)gera o plano mínimo da norma para a localidade. Regras editadas à
    mão (manual=True) são preservadas; as automáticas são substituídas."""
    _validar_localidade(localidade)
    config = _config_ou_404(db, localidade)
    novas, avisos = regras_norma.gerar_regras_padrao(
        config.populacao_abastecida, config.manancial, config.filtracao, config.numero_filtros or 1,
    )

    db.query(models.RegraAmostragem).filter(
        models.RegraAmostragem.localidade == localidade, models.RegraAmostragem.manual == False  # noqa: E712
    ).delete()
    manuais = db.query(models.RegraAmostragem).filter(models.RegraAmostragem.localidade == localidade).all()
    grupos_manuais = {r.grupo for r in manuais}
    for r in novas:
        if r["grupo"] in grupos_manuais:
            continue
        db.add(models.RegraAmostragem(localidade=localidade, manual=False, ativo=True, **r))
    db.commit()

    todas = db.query(models.RegraAmostragem).filter(models.RegraAmostragem.localidade == localidade).order_by(models.RegraAmostragem.id).all()
    return schemas.GerarRegrasOut(regras=todas, avisos=avisos)


@router.get("/regras", response_model=List[schemas.RegraAmostragemOut])
def listar_regras(localidade: Optional[str] = None, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    query = db.query(models.RegraAmostragem)
    if localidade:
        query = query.filter(models.RegraAmostragem.localidade == localidade)
    return query.order_by(models.RegraAmostragem.localidade, models.RegraAmostragem.id).all()


@router.patch("/regras/{regra_id}", response_model=schemas.RegraAmostragemOut)
def editar_regra(regra_id: int, dados: schemas.RegraAmostragemUpdate, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(auth.exigir_tipo("admin"))):
    regra = db.query(models.RegraAmostragem).filter(models.RegraAmostragem.id == regra_id).first()
    if not regra:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    if dados.periodo is not None and dados.periodo not in regras_norma.PERIODOS:
        raise HTTPException(status_code=400, detail=f"Período inválido. Use: {', '.join(regras_norma.PERIODOS)}")
    if dados.quantidade is not None and dados.quantidade < 0:
        raise HTTPException(status_code=400, detail="Quantidade não pode ser negativa")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(regra, campo, valor)
    regra.manual = True
    db.commit()
    db.refresh(regra)
    return regra


# ----------------------------------------------------------------------------
# Pontos de coleta
# ----------------------------------------------------------------------------

@router.post("/pontos", response_model=schemas.PontoColetaOut)
def criar_ponto(dados: schemas.PontoColetaCreate, db: Session = Depends(get_db),
                usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "quimico"))):
    _validar_localidade(dados.localidade)
    if dados.tipo not in regras_norma.TIPOS_PONTO:
        raise HTTPException(status_code=400, detail=f"Tipo de ponto inválido. Use: {', '.join(regras_norma.TIPOS_PONTO)}")
    ponto = models.PontoColeta(**dados.model_dump())
    db.add(ponto)
    db.commit()
    db.refresh(ponto)
    return ponto


@router.get("/pontos", response_model=List[schemas.PontoColetaOut])
def listar_pontos(localidade: Optional[str] = None, tipo: Optional[str] = None, incluir_inativos: bool = False,
                  db: Session = Depends(get_db), usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    query = db.query(models.PontoColeta)
    if localidade:
        query = query.filter(models.PontoColeta.localidade == localidade)
    if tipo:
        query = query.filter(models.PontoColeta.tipo == tipo)
    if not incluir_inativos:
        query = query.filter(models.PontoColeta.ativo == True)  # noqa: E712
    return query.order_by(models.PontoColeta.localidade, models.PontoColeta.tipo, models.PontoColeta.nome).all()


@router.patch("/pontos/{ponto_id}", response_model=schemas.PontoColetaOut)
def editar_ponto(ponto_id: int, dados: schemas.PontoColetaUpdate, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(auth.exigir_tipo("admin", "quimico"))):
    ponto = db.query(models.PontoColeta).filter(models.PontoColeta.id == ponto_id).first()
    if not ponto:
        raise HTTPException(status_code=404, detail="Ponto não encontrado")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(ponto, campo, valor)
    db.commit()
    db.refresh(ponto)
    return ponto


# ----------------------------------------------------------------------------
# Amostras
# ----------------------------------------------------------------------------

@router.post("/amostras", response_model=schemas.AmostraOut)
def criar_amostra(dados: schemas.AmostraCreate, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(auth.exigir_tipo(*ESCRITA_LAB))):
    ponto = db.query(models.PontoColeta).filter(models.PontoColeta.id == dados.ponto_id).first()
    if not ponto or not ponto.ativo:
        raise HTTPException(status_code=404, detail="Ponto de coleta não encontrado ou inativo")
    tipos_ok = regras_norma.GRUPO_PONTO_TIPO.get(dados.grupo)
    if not tipos_ok:
        raise HTTPException(status_code=400, detail=f"Grupo inválido para amostra. Use: {', '.join(regras_norma.GRUPO_PONTO_TIPO)}")
    if ponto.tipo not in tipos_ok:
        raise HTTPException(status_code=400, detail=f"O grupo '{dados.grupo}' só pode ser coletado em ponto do tipo: {', '.join(tipos_ok)}")

    pendente = dados.data_prevista is not None and dados.coletado_em is None
    coletado_em = None if pendente else (dados.coletado_em or datetime.now())

    amostra = models.Amostra(
        localidade=ponto.localidade, ponto_id=ponto.id, grupo=dados.grupo,
        status="pendente" if pendente else "coletada",
        data_prevista=dados.data_prevista, coletado_em=coletado_em,
        coletor_id=None if pendente else usuario.id,
        cloro_residual=dados.cloro_residual, cor_aparente=dados.cor_aparente,
        turbidez=dados.turbidez, ph=dados.ph, observacoes=dados.observacoes,
    )
    db.add(amostra)
    db.flush()
    amostra.codigo = _novo_codigo(amostra, coletado_em or datetime.combine(dados.data_prevista, datetime.min.time()))
    db.commit()
    db.refresh(amostra)
    return amostra


@router.patch("/amostras/{amostra_id}/coleta", response_model=schemas.AmostraOut)
def registrar_coleta(amostra_id: int, dados: schemas.AmostraColeta, db: Session = Depends(get_db),
                     usuario: models.Usuario = Depends(auth.exigir_tipo(*ESCRITA_LAB))):
    """Registra a coleta de uma amostra que estava pendente (ex.: recoleta)."""
    amostra = db.query(models.Amostra).filter(models.Amostra.id == amostra_id).first()
    if not amostra:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")
    if amostra.status != "pendente":
        raise HTTPException(status_code=400, detail="Só amostras pendentes podem ter a coleta registrada")
    amostra.coletado_em = dados.coletado_em or datetime.now()
    amostra.coletor_id = usuario.id
    amostra.status = "coletada"
    for campo in ("cloro_residual", "cor_aparente", "turbidez", "ph", "observacoes"):
        valor = getattr(dados, campo)
        if valor is not None:
            setattr(amostra, campo, valor)
    db.commit()
    db.refresh(amostra)
    return amostra


@router.get("/amostras", response_model=List[schemas.AmostraOut])
def listar_amostras(localidade: Optional[str] = None, grupo: Optional[str] = None, status: Optional[str] = None,
                    mes: Optional[str] = None, apenas_recoletas: bool = False,
                    db: Session = Depends(get_db), usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    query = db.query(models.Amostra)
    if localidade:
        query = query.filter(models.Amostra.localidade == localidade)
    if grupo:
        query = query.filter(models.Amostra.grupo == grupo)
    if status:
        query = query.filter(models.Amostra.status == status)
    if apenas_recoletas:
        query = query.filter(models.Amostra.recoleta_de_id.isnot(None))
    if mes:
        ano, m = _parse_mes(mes)
        ini, fim = _intervalo(date(ano, m, 1), regras_norma._fim_do_mes(ano, m))
        query = query.filter(
            ((models.Amostra.coletado_em >= ini) & (models.Amostra.coletado_em <= fim))
            | ((models.Amostra.coletado_em.is_(None)) & (models.Amostra.data_prevista >= ini.date()) & (models.Amostra.data_prevista <= fim.date()))
        )
    return query.order_by(models.Amostra.id.desc()).limit(500).all()


@router.post("/amostras/{amostra_id}/encaminhar", response_model=schemas.AmostraOut)
def encaminhar_amostra(amostra_id: int, db: Session = Depends(get_db),
                       usuario: models.Usuario = Depends(auth.exigir_tipo(*ESCRITA_LAB))):
    """Marca a amostra como enviada ao laboratório externo."""
    amostra = db.query(models.Amostra).filter(models.Amostra.id == amostra_id).first()
    if not amostra:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")
    if amostra.status not in ("coletada", "analisada"):
        raise HTTPException(status_code=400, detail="Só amostras já coletadas podem ser encaminhadas")
    amostra.status = "encaminhada"
    db.commit()
    db.refresh(amostra)
    return amostra


def _ultimos_ecoli_12_meses(db: Session, localidade: str, ate: datetime):
    desde = ate - timedelta(days=365)
    linhas = (
        db.query(models.ResultadoAnalise.e_coli_nmp, models.Amostra.coletado_em)
        .join(models.Amostra, models.Amostra.id == models.ResultadoAnalise.amostra_id)
        .filter(
            models.Amostra.localidade == localidade,
            models.Amostra.grupo == "ecoli_captacao",
            models.Amostra.coletado_em >= desde,
            models.Amostra.coletado_em <= ate,
            models.ResultadoAnalise.e_coli_nmp.isnot(None),
        )
        .order_by(models.Amostra.coletado_em)
        .all()
    )
    return [(float(v), q) for v, q in linhas]


@router.post("/amostras/{amostra_id}/resultado", response_model=schemas.ResultadoComRecoletas)
def lancar_resultado(amostra_id: int, dados: schemas.ResultadoAnaliseCreate, db: Session = Depends(get_db),
                     usuario: models.Usuario = Depends(auth.exigir_tipo(*ESCRITA_LAB))):
    amostra = db.query(models.Amostra).filter(models.Amostra.id == amostra_id).first()
    if not amostra:
        raise HTTPException(status_code=404, detail="Amostra não encontrada")
    if amostra.status == "pendente":
        raise HTTPException(status_code=400, detail="Registre primeiro a coleta da amostra (ela ainda está pendente)")
    if amostra.status == "cancelada":
        raise HTTPException(status_code=400, detail="Amostra cancelada")
    if db.query(models.ResultadoAnalise).filter(models.ResultadoAnalise.amostra_id == amostra.id).first():
        raise HTTPException(status_code=409, detail="Esta amostra já tem resultado lançado")
    if amostra.grupo == "agua_bruta_semestral":
        raise HTTPException(status_code=400, detail="Água bruta semestral é registrada pelo laudo do laboratório externo (POST /qualidade/laudos)")

    ponto = db.query(models.PontoColeta).filter(models.PontoColeta.id == amostra.ponto_id).first()
    alertas: List[str] = []
    conforme: Optional[bool] = None
    exige_recoleta = False

    if amostra.grupo in GRUPOS_BACTERIOLOGICOS:
        if dados.coliformes_totais_presente is None or dados.e_coli_presente is None:
            raise HTTPException(status_code=400, detail="Informe coliformes totais E E. coli (presente/ausente)")
        conforme, alertas, exige_recoleta = regras_norma.avaliar_bacteriologia(
            ponto.tipo, dados.coliformes_totais_presente, dados.e_coli_presente,
        )
        faltando = [n for n, v in (("cloro residual", amostra.cloro_residual), ("cor aparente", amostra.cor_aparente), ("turbidez", amostra.turbidez)) if v is None]
        if faltando:
            alertas.append(f"Faltou medir na coleta: {', '.join(faltando)} (obrigatório em toda amostra bacteriológica — Art. 44 §3)")
    elif amostra.grupo == "ecoli_captacao":
        if dados.e_coli_nmp is None:
            raise HTTPException(status_code=400, detail="Informe a contagem de E. coli (NMP/100 mL)")
    elif amostra.grupo == "cianobacterias":
        if dados.cianobacterias_cel_ml is None:
            raise HTTPException(status_code=400, detail="Informe a contagem de cianobactérias (células/mL)")
        if dados.cianobacterias_cel_ml > regras_norma.LIMITE_CIANOBACTERIAS_CIANOTOXINAS:
            alertas.append("Acima de 20.000 células/mL: análise de cianotoxinas no ponto de captação no mínimo SEMANAL (Art. 43 §2)")
        elif dados.cianobacterias_cel_ml > regras_norma.LIMITE_CIANOBACTERIAS_SEMANAL:
            alertas.append("Acima de 10.000 células/mL: monitoramento de cianobactérias passa a SEMANAL (Anexo 12)")

    resultado = models.ResultadoAnalise(
        amostra_id=amostra.id, analista_id=usuario.id, conforme=conforme,
        **dados.model_dump(),
    )
    db.add(resultado)
    amostra.status = "analisada"
    db.flush()

    if amostra.grupo == "ecoli_captacao":
        serie = _ultimos_ecoli_12_meses(db, amostra.localidade, (amostra.coletado_em or datetime.now()) + timedelta(seconds=1))
        valores = [v for v, _ in serie]
        if dados.e_coli_nmp is not None and not any(abs(v - float(dados.e_coli_nmp)) < 1e-9 for v in valores):
            valores.append(float(dados.e_coli_nmp))
        gm = regras_norma.media_geometrica(valores)
        if gm is not None and gm >= regras_norma.LIMITE_ECOLI_BRUTA_MEDIA_GEOMETRICA:
            alertas.append(
                f"Média geométrica de E. coli na captação (12 meses) = {gm:.0f} NMP/100 mL, igual ou acima de 1.000: "
                "avaliar a ETA com monitoramento SEMANAL de esporos de bactérias aeróbias (Art. 29 §1)."
            )

    resultado.alertas = json.dumps(alertas, ensure_ascii=False) if alertas else None

    recoletas: List[models.Amostra] = []
    if exige_recoleta and amostra.grupo in GRUPOS_BACTERIOLOGICOS:
        base = (amostra.coletado_em or datetime.now()).date()
        for item in regras_norma.plano_recoleta(ponto.tipo, base):
            rec = models.Amostra(
                localidade=amostra.localidade, ponto_id=amostra.ponto_id, grupo=amostra.grupo,
                status="pendente", data_prevista=item["data_prevista"],
                recoleta_de_id=amostra.id, posicao_recoleta=item["posicao_recoleta"],
                observacoes=f"Recoleta da amostra {amostra.codigo} (resultado positivo) — Art. 27",
            )
            db.add(rec)
            db.flush()
            rec.codigo = _novo_codigo(rec, datetime.combine(item["data_prevista"], datetime.min.time()))
            recoletas.append(rec)
        alertas.append(
            "Resultado POSITIVO: ações corretivas e recoleta em dias sucessivos até resultado satisfatório; "
            "informar as medidas à autoridade de saúde (Art. 27)."
        )
        resultado.alertas = json.dumps(alertas, ensure_ascii=False)

    db.commit()
    db.refresh(resultado)
    for r in recoletas:
        db.refresh(r)
    return schemas.ResultadoComRecoletas(resultado=resultado, alertas=alertas, recoletas_criadas=recoletas)


@router.get("/amostras/{amostra_id}/resultado", response_model=schemas.ResultadoAnaliseOut)
def ver_resultado(amostra_id: int, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    res = db.query(models.ResultadoAnalise).filter(models.ResultadoAnalise.amostra_id == amostra_id).first()
    if not res:
        raise HTTPException(status_code=404, detail="Esta amostra ainda não tem resultado")
    return res


# ----------------------------------------------------------------------------
# Laudos do laboratório externo
# ----------------------------------------------------------------------------

@router.post("/laudos", response_model=schemas.LaudoExternoOut)
async def registrar_laudo(
    localidade: str = Form(...),
    tipo: str = Form(...),
    laboratorio: str = Form(...),
    data_coleta: date = Form(...),
    numero_laudo: Optional[str] = Form(None),
    data_emissao: Optional[date] = Form(None),
    parametros_resumo: Optional[str] = Form(None),
    conforme: Optional[bool] = Form(None),
    ponto_id: Optional[int] = Form(None),
    amostra_id: Optional[int] = Form(None),
    observacoes: Optional[str] = Form(None),
    arquivo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(auth.exigir_tipo(*ESCRITA_LAB)),
):
    _validar_localidade(localidade)
    if tipo not in TIPOS_LAUDO:
        raise HTTPException(status_code=400, detail=f"Tipo de laudo inválido. Use: {', '.join(TIPOS_LAUDO)}")

    amostra = None
    if amostra_id is not None:
        amostra = db.query(models.Amostra).filter(models.Amostra.id == amostra_id).first()
        if not amostra:
            raise HTTPException(status_code=404, detail="Amostra não encontrada")
    if ponto_id is not None and not db.query(models.PontoColeta).filter(models.PontoColeta.id == ponto_id).first():
        raise HTTPException(status_code=404, detail="Ponto de coleta não encontrado")

    nome_arquivo = None
    if arquivo is not None and arquivo.filename:
        extensao = os.path.splitext(arquivo.filename)[1].lower()
        if extensao not in EXTENSOES_LAUDO:
            raise HTTPException(status_code=400, detail="Anexe o laudo em PDF, JPG ou PNG")
        conteudo = await arquivo.read()
        if len(conteudo) > TAMANHO_MAX_LAUDO:
            raise HTTPException(status_code=400, detail="Arquivo maior que 15 MB")
        os.makedirs(PASTA_LAUDOS, exist_ok=True)
        nome_arquivo = f"{uuid.uuid4().hex}{extensao}"
        with open(os.path.join(PASTA_LAUDOS, nome_arquivo), "wb") as f:
            f.write(conteudo)

    laudo = models.LaudoExterno(
        localidade=localidade, ponto_id=ponto_id, amostra_id=amostra_id, tipo=tipo, laboratorio=laboratorio,
        numero_laudo=numero_laudo, data_coleta=data_coleta, data_emissao=data_emissao,
        parametros_resumo=parametros_resumo, conforme=conforme, arquivo=nome_arquivo,
        observacoes=observacoes, registrado_por=usuario.id,
    )
    db.add(laudo)
    if amostra is not None and amostra.status in ("coletada", "analisada", "encaminhada"):
        amostra.status = "laudo_recebido"
    db.commit()
    db.refresh(laudo)
    return _laudo_out(laudo)


@router.get("/laudos", response_model=List[schemas.LaudoExternoOut])
def listar_laudos(localidade: Optional[str] = None, tipo: Optional[str] = None, db: Session = Depends(get_db),
                  usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    query = db.query(models.LaudoExterno)
    if localidade:
        query = query.filter(models.LaudoExterno.localidade == localidade)
    if tipo:
        query = query.filter(models.LaudoExterno.tipo == tipo)
    return [_laudo_out(l) for l in query.order_by(models.LaudoExterno.data_coleta.desc()).limit(200).all()]


@router.get("/laudos/{laudo_id}/arquivo")
def baixar_laudo(laudo_id: int, db: Session = Depends(get_db),
                 usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    laudo = db.query(models.LaudoExterno).filter(models.LaudoExterno.id == laudo_id).first()
    if not laudo or not laudo.arquivo:
        raise HTTPException(status_code=404, detail="Laudo ou arquivo não encontrado")
    caminho = os.path.join(PASTA_LAUDOS, os.path.basename(laudo.arquivo))
    if not os.path.exists(caminho):
        raise HTTPException(status_code=404, detail="Arquivo do laudo não está mais no servidor")
    return FileResponse(caminho, filename=f"laudo-{laudo.numero_laudo or laudo.id}{os.path.splitext(caminho)[1]}")


# ----------------------------------------------------------------------------
# Conformidade (exigido x realizado)
# ----------------------------------------------------------------------------

def _realizado(db: Session, regra: models.RegraAmostragem, ini: date, fim: date) -> int:
    i, f = _intervalo(ini, fim)
    if regra.grupo in ("fq_saida", "turbidez_filtro"):
        q = db.query(models.AnaliseEta).filter(
            models.AnaliseEta.localidade == regra.localidade,
            models.AnaliseEta.coletado_em >= i, models.AnaliseEta.coletado_em <= f,
        )
        if regra.grupo == "turbidez_filtro":
            q = q.filter(models.AnaliseEta.turbidez_filtrada.isnot(None))
        return q.count()
    if regra.grupo == "agua_bruta_semestral":
        return db.query(models.LaudoExterno).filter(
            models.LaudoExterno.localidade == regra.localidade,
            models.LaudoExterno.tipo == "agua_bruta_semestral",
            models.LaudoExterno.data_coleta >= ini, models.LaudoExterno.data_coleta <= fim,
        ).count()
    return db.query(models.Amostra).filter(
        models.Amostra.localidade == regra.localidade,
        models.Amostra.grupo == regra.grupo,
        models.Amostra.status.in_(("coletada", "analisada", "encaminhada", "laudo_recebido")),
        models.Amostra.recoleta_de_id.is_(None),  # recoleta não conta no mínimo (Art. 44 §2)
        models.Amostra.coletado_em >= i, models.Amostra.coletado_em <= f,
    ).count()


def _periodo_efetivo_cianobacterias(db: Session, localidade: str):
    ultimo = (
        db.query(models.ResultadoAnalise.cianobacterias_cel_ml)
        .join(models.Amostra, models.Amostra.id == models.ResultadoAnalise.amostra_id)
        .filter(models.Amostra.localidade == localidade, models.Amostra.grupo == "cianobacterias",
                models.ResultadoAnalise.cianobacterias_cel_ml.isnot(None))
        .order_by(models.Amostra.coletado_em.desc())
        .first()
    )
    if ultimo and float(ultimo[0]) > regras_norma.LIMITE_CIANOBACTERIAS_SEMANAL:
        return "semana", float(ultimo[0])
    return None, (float(ultimo[0]) if ultimo else None)


def calcular_conformidade(db: Session, localidade: str, ano: int, mes: int, hoje: date) -> dict:
    config = db.query(models.ConfigSistemaAgua).filter(models.ConfigSistemaAgua.localidade == localidade).first()
    regras = db.query(models.RegraAmostragem).filter(
        models.RegraAmostragem.localidade == localidade, models.RegraAmostragem.ativo == True  # noqa: E712
    ).order_by(models.RegraAmostragem.id).all()

    itens = []
    for regra in regras:
        periodo = regra.periodo
        quantidade = regra.quantidade
        nota = None
        if regra.grupo == "cianobacterias":
            efetivo, ultimo = _periodo_efetivo_cianobacterias(db, localidade)
            if efetivo:
                periodo = efetivo
                nota = f"Última contagem {ultimo:,.0f} células/mL (> 10.000): frequência semanal (Anexo 12).".replace(",", ".")

        janelas = regras_norma.janelas_da_regra(periodo, ano, mes, hoje)
        exigido_total = 0
        realizado_total = 0
        realizado_bruto = 0
        deficits = []
        status = "ok"
        for ini, fim, encerrada in janelas:
            realizado = _realizado(db, regra, ini, fim)
            exigido_total += quantidade
            realizado_total += min(realizado, quantidade)
            realizado_bruto += realizado
            st = regras_norma.status_regra(quantidade, realizado, encerrada)
            if st == "deficit":
                status = "deficit"
            elif st == "em_andamento" and status == "ok":
                status = "em_andamento"
            if st != "ok" and len(deficits) < 40:
                deficits.append({"inicio": ini.isoformat(), "fim": fim.isoformat(), "exigido": quantidade,
                                 "realizado": realizado, "encerrada": encerrada})
        itens.append({
            "regra_id": regra.id, "grupo": regra.grupo,
            "descricao": regras_norma.GRUPOS.get(regra.grupo, regra.grupo),
            "norma": regra.norma, "ponto_tipo": regra.ponto_tipo,
            "periodo": periodo, "quantidade_por_periodo": quantidade,
            "exigido": exigido_total, "realizado": realizado_total, "realizado_bruto": realizado_bruto,
            "percentual": round(100.0 * realizado_total / exigido_total, 1) if exigido_total else None,
            "status": status, "janelas_pendentes": deficits, "nota": nota,
        })

    # Padrão bacteriológico mensal na rede
    ini_mes, fim_mes = _intervalo(date(ano, mes, 1), regras_norma._fim_do_mes(ano, mes))
    amostras_rede = (
        db.query(models.ResultadoAnalise)
        .join(models.Amostra, models.Amostra.id == models.ResultadoAnalise.amostra_id)
        .filter(models.Amostra.localidade == localidade, models.Amostra.grupo == "bact_rede",
                models.Amostra.recoleta_de_id.is_(None),
                models.Amostra.coletado_em >= ini_mes, models.Amostra.coletado_em <= fim_mes)
        .all()
    )
    total = len(amostras_rede)
    com_ct = sum(1 for r in amostras_rede if r.coliformes_totais_presente)
    com_ec = sum(1 for r in amostras_rede if r.e_coli_presente)
    populacao = config.populacao_abastecida if config else 0
    status_rede, textos_rede = regras_norma.avaliar_mes_rede(populacao, total, com_ct, com_ec)

    # Recoletas pendentes
    pendentes = db.query(models.Amostra).filter(
        models.Amostra.localidade == localidade, models.Amostra.status == "pendente",
        models.Amostra.recoleta_de_id.isnot(None),
    ).order_by(models.Amostra.data_prevista).all()
    recoletas = [{
        "amostra_id": a.id, "codigo": a.codigo, "ponto_id": a.ponto_id, "grupo": a.grupo,
        "posicao": a.posicao_recoleta, "data_prevista": a.data_prevista.isoformat() if a.data_prevista else None,
        "atrasada": bool(a.data_prevista and a.data_prevista < hoje),
    } for a in pendentes]

    # Alertas gerais
    alertas = []
    serie = _ultimos_ecoli_12_meses(db, localidade, datetime.combine(hoje, datetime.max.time()))
    gm = regras_norma.media_geometrica([v for v, _ in serie])
    if gm is not None and gm >= regras_norma.LIMITE_ECOLI_BRUTA_MEDIA_GEOMETRICA:
        alertas.append(f"Média geométrica de E. coli na captação = {gm:.0f} (>= 1.000): monitoramento semanal de esporos de bactérias aeróbias na ETA (Art. 29 §1).")
    _, ultimo_cian = _periodo_efetivo_cianobacterias(db, localidade)
    if ultimo_cian and ultimo_cian > regras_norma.LIMITE_CIANOBACTERIAS_CIANOTOXINAS:
        alertas.append("Cianobactérias acima de 20.000 células/mL: cianotoxinas no ponto de captação no mínimo semanais (Art. 43 §2).")
    if any(r["atrasada"] for r in recoletas):
        alertas.append("Há recoleta(s) ATRASADA(S) após resultado positivo (Art. 27).")
    if not regras:
        alertas.append("Plano de amostragem não gerado para esta localidade.")

    return {
        "localidade": localidade, "mes": f"{ano:04d}-{mes:02d}", "hoje": hoje.isoformat(),
        "populacao_abastecida": populacao,
        "manancial": config.manancial if config else None,
        "filtracao": config.filtracao if config else None,
        "regras": itens,
        "rede": {"status": status_rede, "textos": textos_rede, "amostras_analisadas": total,
                 "com_coliformes_totais": com_ct, "com_e_coli": com_ec},
        "recoletas_pendentes": recoletas,
        "ecoli_captacao_media_geometrica_12m": round(gm, 1) if gm is not None else None,
        "alertas": alertas,
    }


@router.get("/conformidade")
def conformidade(localidade: str, mes: Optional[str] = None, ate: Optional[date] = None,
                 db: Session = Depends(get_db), usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    """`ate` (opcional) permite consultar como se hoje fosse outra data."""
    _validar_localidade(localidade)
    ano, m = _parse_mes(mes)
    return calcular_conformidade(db, localidade, ano, m, ate or date.today())


@router.get("/ecoli-captacao/{localidade}")
def ecoli_captacao(localidade: str, db: Session = Depends(get_db),
                   usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    """Série mensal de E. coli na captação e média geométrica móvel de 12 meses (Art. 29)."""
    _validar_localidade(localidade)
    serie = _ultimos_ecoli_12_meses(db, localidade, datetime.now())
    gm = regras_norma.media_geometrica([v for v, _ in serie])
    return {
        "localidade": localidade,
        "medicoes": [{"coletado_em": q.isoformat(), "e_coli_nmp_100ml": v} for v, q in serie],
        "media_geometrica_12m": round(gm, 1) if gm is not None else None,
        "limite": regras_norma.LIMITE_ECOLI_BRUTA_MEDIA_GEOMETRICA,
        "acima_do_limite": bool(gm is not None and gm >= regras_norma.LIMITE_ECOLI_BRUTA_MEDIA_GEOMETRICA),
        "observacao": "Valores 0 são tratados como 1 NMP/100 mL no cálculo (a média geométrica não existe para zero).",
    }


@router.get("/relatorio-mensal-pdf")
def relatorio_mensal_pdf(localidade: str, mes: Optional[str] = None, ate: Optional[date] = None,
                         db: Session = Depends(get_db), usuario: models.Usuario = Depends(auth.exigir_tipo(*LEITURA))):
    from pdf_qualidade import gerar_relatorio_mensal
    _validar_localidade(localidade)
    ano, m = _parse_mes(mes)
    dados = calcular_conformidade(db, localidade, ano, m, ate or date.today())

    ini, fim = _intervalo(date(ano, m, 1), regras_norma._fim_do_mes(ano, m))
    linhas = (
        db.query(models.Amostra, models.PontoColeta, models.ResultadoAnalise)
        .join(models.PontoColeta, models.PontoColeta.id == models.Amostra.ponto_id)
        .outerjoin(models.ResultadoAnalise, models.ResultadoAnalise.amostra_id == models.Amostra.id)
        .filter(models.Amostra.localidade == localidade, models.Amostra.coletado_em >= ini, models.Amostra.coletado_em <= fim)
        .order_by(models.Amostra.coletado_em).all()
    )
    amostras = []
    for a, p, r in linhas:
        amostras.append({
            "codigo": a.codigo, "data": a.coletado_em.strftime("%d/%m/%Y %H:%M") if a.coletado_em else "",
            "ponto": p.nome, "grupo": a.grupo, "recoleta": a.recoleta_de_id is not None,
            "coliformes": None if r is None else r.coliformes_totais_presente,
            "e_coli": None if r is None else r.e_coli_presente,
            "e_coli_nmp": None if r is None or r.e_coli_nmp is None else float(r.e_coli_nmp),
            "conforme": None if r is None else r.conforme,
        })
    pdf = gerar_relatorio_mensal(dados, amostras)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="qualidade-agua-{localidade}-{ano}-{m:02d}.pdf"'})
