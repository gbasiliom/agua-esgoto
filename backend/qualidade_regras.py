"""
Regras de qualidade da água — Portaria GM/MS nº 888/2021 (Anexo XX da
Portaria de Consolidação nº 5/2017, alterado).

Este arquivo NÃO acessa banco de dados: só contém as regras (números mínimos
de amostragem, critérios de conformidade bacteriológica, recoleta) para poder
ser testado isoladamente. Cada regra aponta o artigo/anexo de onde saiu.

IMPORTANTE: as quantidades abaixo vieram da versão do Diário Oficial da
Portaria 888/2021 (que o próprio texto diz não substituir a versão
certificada). A tabela do Anexo 14 para populações a partir de 10.000
habitantes veio embaralhada no PDF e, de propósito, NÃO foi codificada aqui:
nesse caso o mínimo da rede precisa ser informado manualmente (o gerador
devolve um aviso). Todas as regras geradas são editáveis depois, e podem ser
trocadas pelo que a Vigilância Sanitária aprovar no plano de amostragem do
sistema (Art. 41/44 — o plano é proposto pelo responsável e recebe parecer da
autoridade municipal de saúde).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------
# Vocabulário
# ----------------------------------------------------------------------------

TIPOS_PONTO = ["captacao", "saida_eta", "reservatorio", "rede"]

# Grupos de amostragem (o que cada regra controla)
GRUPOS = {
    "fq_saida": "Físico-química na saída da ETA (turbidez, cloro residual, cor, pH)",
    "turbidez_filtro": "Turbidez do efluente do filtro",
    "bact_saida": "Bacteriologia na saída do tratamento (E. coli e coliformes totais)",
    "bact_rede": "Bacteriologia na rede e reservatórios (E. coli e coliformes totais)",
    "ecoli_captacao": "E. coli na água bruta — captação (mensal)",
    "agua_bruta_semestral": "Parâmetros da água bruta (análise semestral — laudo externo)",
    "cianobacterias": "Cianobactérias no manancial (Anexo 12)",
}

# De qual tipo de ponto cada grupo de amostra deve ser coletada
GRUPO_PONTO_TIPO = {
    "bact_saida": ("saida_eta",),
    "bact_rede": ("rede", "reservatorio"),
    "ecoli_captacao": ("captacao",),
    "agua_bruta_semestral": ("captacao",),
    "cianobacterias": ("captacao",),
}

PERIODOS = ["dia", "semana", "mes", "trimestre", "semestre"]

# Limite de turbidez/E. coli na água bruta que dispara avaliação reforçada da ETA
LIMITE_ECOLI_BRUTA_MEDIA_GEOMETRICA = 1000.0  # E. coli/100 mL
LIMITE_CIANOBACTERIAS_SEMANAL = 10_000  # células/mL — acima disso, monitoramento semanal (Anexo 12)
LIMITE_CIANOBACTERIAS_CIANOTOXINAS = 20_000  # células/mL — acima disso, cianotoxinas no mínimo semanais (Art. 43 §2)
POPULACAO_LIMITE_95_PORCENTO = 20_000  # Anexo 1: >= 20.000 hab. => 95% das amostras do mês sem coliformes totais na rede


# ----------------------------------------------------------------------------
# Geração das regras padrão de amostragem de um sistema (uma localidade)
# ----------------------------------------------------------------------------

def minimo_bacteriologico_rede(populacao: int) -> Optional[int]:
    """Anexo 14 — nº mínimo MENSAL de amostras na rede/reservatórios.
    Só as duas primeiras faixas foram codificadas (ver aviso no topo)."""
    if populacao < 5000:
        return 5
    if populacao <= 10000:
        return 10
    return None


def gerar_regras_padrao(populacao: int, manancial: str, filtracao: Optional[str],
                        numero_filtros: int = 1) -> Tuple[List[Dict], List[str]]:
    """Devolve (lista de regras, lista de avisos)."""
    regras: List[Dict] = []
    avisos: List[str] = []
    superficial = manancial == "superficial"

    # Anexo 13 — saída do tratamento
    if superficial:
        regras.append(dict(grupo="fq_saida", ponto_tipo="saida_eta", quantidade=12, periodo="dia",
                           norma="Anexo 13", observacao="1 amostra a cada 2 horas: turbidez, cloro residual, cor aparente e pH."))
    else:
        regras.append(dict(grupo="fq_saida", ponto_tipo="saida_eta", quantidade=1, periodo="semana",
                           norma="Anexo 13", observacao="Manancial subterrâneo: 1 amostra por semana."))

    # Art. 28 §3 — turbidez do efluente de cada unidade de filtração
    if superficial:
        if filtracao == "rapida":
            regras.append(dict(grupo="turbidez_filtro", ponto_tipo="saida_eta", quantidade=12 * max(numero_filtros, 1),
                               periodo="dia", norma="Art. 28 §3",
                               observacao="Filtração rápida: a cada 2 horas, em cada unidade de filtração."))
        else:
            regras.append(dict(grupo="turbidez_filtro", ponto_tipo="saida_eta", quantidade=1 * max(numero_filtros, 1),
                               periodo="dia", norma="Art. 28 §3",
                               observacao="Filtração lenta: diariamente, em cada unidade de filtração."))

    # Anexo 14 — bacteriologia na saída do tratamento
    regras.append(dict(
        grupo="bact_saida", ponto_tipo="saida_eta",
        quantidade=2 if superficial else 1, periodo="semana", norma="Anexo 14",
        observacao="E. coli e coliformes totais. Superficial: 2 amostras semanais por unidade de tratamento; subterrâneo: 1 semanal.",
    ))

    # Anexo 14 — bacteriologia na rede
    minimo_rede = minimo_bacteriologico_rede(populacao)
    if minimo_rede is None:
        avisos.append(
            "População acima de 10.000 habitantes: o mínimo mensal de amostras na rede (Anexo 14) precisa ser "
            "informado manualmente — a tabela dessa faixa não foi codificada."
        )
    else:
        regras.append(dict(grupo="bact_rede", ponto_tipo="rede", quantidade=minimo_rede, periodo="mes",
                           norma="Anexo 14",
                           observacao="Mínimo mensal de amostras na rede e reservatórios. Recoletas não entram na contagem (Art. 44 §2)."))

    # Art. 29 — E. coli na captação (só manancial superficial)
    if superficial:
        regras.append(dict(grupo="ecoli_captacao", ponto_tipo="captacao", quantidade=1, periodo="mes",
                           norma="Art. 29",
                           observacao="Contagem mensal de E. coli (NMP/100 mL) em cada ponto de captação. Alimenta a média geométrica de 12 meses."))
        regras.append(dict(grupo="cianobacterias", ponto_tipo="captacao", quantidade=1, periodo="trimestre",
                           norma="Anexo 12",
                           observacao="Contagem de cianobactérias: trimestral até 10.000 células/mL; semanal acima disso."))

    # Art. 42 — água bruta semestral
    regras.append(dict(grupo="agua_bruta_semestral", ponto_tipo="captacao", quantidade=1, periodo="semestre",
                       norma="Art. 42",
                       observacao=("Análise semestral da água bruta em cada captação (laudo externo). Superficial: DQO, DBO, OD, turbidez, "
                                   "cor verdadeira, pH, fósforo total, nitrogênio amoniacal, inorgânicos, orgânicos e agrotóxicos."
                                   if superficial else
                                   "Análise semestral da água bruta (subterrâneo): turbidez, cor verdadeira, pH, fósforo total, "
                                   "nitrogênio amoniacal, condutividade, inorgânicos, orgânicos e agrotóxicos.")))
    return regras, avisos


# ----------------------------------------------------------------------------
# Conformidade bacteriológica de uma amostra
# ----------------------------------------------------------------------------

def avaliar_bacteriologia(ponto_tipo: str, coliformes_presente: Optional[bool],
                          ecoli_presente: Optional[bool]) -> Tuple[Optional[bool], List[str], bool]:
    """
    Devolve (conforme, alertas, exige_recoleta).

    Anexo 1: E. coli ausente em 100 mL em qualquer ponto. Coliformes totais
    ausentes na saída do tratamento. Na rede, coliformes totais entram na
    conta mensal (ver avaliar_mes_rede) — a amostra positiva em si é
    registrada como não conforme e sempre gera recoleta (Art. 27).
    Água bruta (captação) não tem padrão de potabilidade: conforme = None.
    """
    if ponto_tipo == "captacao":
        return None, [], False

    alertas: List[str] = []
    if ecoli_presente:
        alertas.append("E. coli PRESENTE — padrão exige ausência em 100 mL")
    if coliformes_presente:
        if ponto_tipo == "saida_eta":
            alertas.append("Coliformes totais PRESENTES na saída do tratamento — padrão exige ausência")
        else:
            alertas.append("Coliformes totais PRESENTES na rede/reservatório (conta no limite mensal)")

    if coliformes_presente is None and ecoli_presente is None:
        return None, [], False

    positivo = bool(ecoli_presente) or bool(coliformes_presente)
    return (not positivo), alertas, positivo


def plano_recoleta(ponto_tipo: str, data_coleta: date) -> List[Dict]:
    """Art. 27 §1-2: novas amostras em dias sucessivos; na rede, no ponto
    positivo + uma a montante + uma a jusante."""
    amanha = data_coleta + timedelta(days=1)
    if ponto_tipo in ("rede", "reservatorio"):
        return [
            dict(posicao_recoleta="mesmo_ponto", data_prevista=amanha),
            dict(posicao_recoleta="montante", data_prevista=amanha),
            dict(posicao_recoleta="jusante", data_prevista=amanha),
        ]
    return [dict(posicao_recoleta="mesmo_ponto", data_prevista=amanha)]


def avaliar_mes_rede(populacao: int, total_analisadas: int, com_coliformes: int,
                     com_ecoli: int) -> Tuple[str, List[str]]:
    """Anexo 1 — padrão microbiológico mensal na rede/reservatórios.
    Considera só amostras de rotina (sem recoletas). Devolve (status, textos)."""
    textos: List[str] = []
    if total_analisadas == 0:
        return "sem_dados", ["Nenhuma amostra analisada neste mês."]
    status = "ok"
    if com_ecoli > 0:
        status = "violacao"
        textos.append(f"E. coli presente em {com_ecoli} amostra(s) — padrão exige ausência em todas.")
    if populacao < POPULACAO_LIMITE_95_PORCENTO:
        if com_coliformes > 1:
            status = "violacao"
            textos.append(f"Coliformes totais em {com_coliformes} amostras — para sistemas com menos de 20.000 hab. só 1 amostra do mês pode ser positiva.")
    else:
        pct_ausente = 100.0 * (total_analisadas - com_coliformes) / total_analisadas
        if pct_ausente < 95.0:
            status = "violacao"
            textos.append(f"Ausência de coliformes totais em {pct_ausente:.1f}% das amostras — exige 95%.")
    if status == "ok" and com_coliformes == 1 and populacao < POPULACAO_LIMITE_95_PORCENTO:
        status = "atencao"
        textos.append("1 amostra positiva para coliformes totais — é o máximo tolerado no mês.")
    return status, textos


# ----------------------------------------------------------------------------
# E. coli na captação — média geométrica móvel de 12 meses (Art. 29 §1)
# ----------------------------------------------------------------------------

def media_geometrica(valores: List[float]) -> Optional[float]:
    """Média geométrica. Valores 0 ou negativos são tratados como 1 NMP/100 mL
    (a média geométrica não existe para zero) — suposição documentada no relatório."""
    if not valores:
        return None
    logs = [math.log(max(float(v), 1.0)) for v in valores]
    return math.exp(sum(logs) / len(logs))


# ----------------------------------------------------------------------------
# Janelas de tempo das regras (para calcular exigido x realizado)
# ----------------------------------------------------------------------------

def _fim_do_mes(ano: int, mes: int) -> date:
    return (date(ano + (mes == 12), (mes % 12) + 1, 1)) - timedelta(days=1)


def janelas_da_regra(periodo: str, ano: int, mes: int, hoje: date) -> List[Tuple[date, date, bool]]:
    """Janelas (inicio, fim, encerrada) que a regra precisa cumprir no mês pedido.
    Para dia: cada dia do mês (até hoje). Para semana: semanas seg-dom cujo
    domingo cai no mês. Mês: o próprio mês. Trimestre/semestre: o período
    civil que contém o mês."""
    inicio_mes = date(ano, mes, 1)
    fim_mes = _fim_do_mes(ano, mes)
    janelas: List[Tuple[date, date, bool]] = []

    if periodo == "dia":
        d = inicio_mes
        while d <= fim_mes and d <= hoje:
            janelas.append((d, d, d < hoje))
            d += timedelta(days=1)
    elif periodo == "semana":
        d = inicio_mes
        # domingos do mês
        while d <= fim_mes:
            if d.weekday() == 6:
                janelas.append((d - timedelta(days=6), d, d < hoje))
            d += timedelta(days=1)
    elif periodo == "mes":
        janelas.append((inicio_mes, fim_mes, fim_mes < hoje))
    elif periodo == "trimestre":
        q0 = ((mes - 1) // 3) * 3 + 1
        ini, fim = date(ano, q0, 1), _fim_do_mes(ano, q0 + 2)
        janelas.append((ini, fim, fim < hoje))
    elif periodo == "semestre":
        s0 = 1 if mes <= 6 else 7
        ini, fim = date(ano, s0, 1), _fim_do_mes(ano, s0 + 5)
        janelas.append((ini, fim, fim < hoje))
    else:
        raise ValueError(f"período inválido: {periodo}")
    return janelas


def status_regra(exigido: int, realizado: int, encerrada: bool) -> str:
    if realizado >= exigido:
        return "ok"
    return "deficit" if encerrada else "em_andamento"
