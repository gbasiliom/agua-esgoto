import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

# Azul marinho (provisório — o tom exato do SAAE-Chalé entra junto com o tema visual dos apps).
COR_PRINCIPAL = colors.HexColor("#0B2A5B")
COR_ALERTA = colors.HexColor("#B42318")
COR_OK = colors.HexColor("#067647")

LOCALIDADE_LABEL = {"sede": "Chalé (sede)", "penha_do_coco": "Penha do Coco", "bananal": "Bananal", "agua_limpa": "Água Limpa"}
STATUS_LABEL = {"ok": "OK", "deficit": "ABAIXO DO MÍNIMO", "em_andamento": "Em andamento"}
GRUPO_LABEL = {
    "fq_saida": "Físico-química (saída ETA)", "turbidez_filtro": "Turbidez do filtro",
    "bact_saida": "Bacteriologia (saída)", "bact_rede": "Bacteriologia (rede)",
    "ecoli_captacao": "E. coli (captação)", "agua_bruta_semestral": "Água bruta semestral",
    "cianobacterias": "Cianobactérias",
}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _sim_nao(valor):
    if valor is None:
        return "—"
    return "Presente" if valor else "Ausente"


def gerar_relatorio_mensal(dados: dict, amostras: list) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            leftMargin=1.8 * cm, rightMargin=1.8 * cm)
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("T", parent=estilos["Title"], textColor=COR_PRINCIPAL, alignment=TA_CENTER, fontSize=17)
    sub = ParagraphStyle("S", parent=estilos["Normal"], alignment=TA_CENTER, textColor=colors.HexColor("#475467"))
    h2 = ParagraphStyle("H2", parent=estilos["Heading2"], textColor=COR_PRINCIPAL, spaceBefore=12, fontSize=12)
    peq = ParagraphStyle("P", parent=estilos["Normal"], fontSize=8.5, leading=11)
    normal = estilos["Normal"]

    ano, mes = dados["mes"].split("-")
    elementos = [
        Paragraph("Relatório mensal de qualidade da água", titulo),
        Paragraph(f"{LOCALIDADE_LABEL.get(dados['localidade'], dados['localidade'])} — {MESES[int(mes) - 1]} de {ano}", sub),
        Spacer(1, 0.2 * cm), HRFlowable(width="100%", color=COR_PRINCIPAL), Spacer(1, 0.2 * cm),
    ]

    elementos.append(Paragraph(
        f"Sistema: população abastecida {dados.get('populacao_abastecida') or '—'} hab.; manancial {dados.get('manancial') or '—'}"
        f"{'; filtração ' + dados['filtracao'] if dados.get('filtracao') else ''}. "
        "Referência: Portaria GM/MS nº 888/2021.", peq))

    if dados["alertas"]:
        elementos.append(Paragraph("Alertas", h2))
        for a in dados["alertas"]:
            elementos.append(Paragraph(f"• {a}", ParagraphStyle("A", parent=peq, textColor=COR_ALERTA)))

    # Exigido x realizado
    elementos.append(Paragraph("Amostragem: exigido x realizado", h2))
    linhas = [["Controle", "Norma", "Exigido", "Realizado", "%", "Situação"]]
    for r in dados["regras"]:
        linhas.append([
            Paragraph(GRUPO_LABEL.get(r["grupo"], r["grupo"]), peq), r["norma"] or "", str(r["exigido"]),
            str(r["realizado"]), "—" if r["percentual"] is None else f"{r['percentual']:.0f}%",
            STATUS_LABEL.get(r["status"], r["status"]),
        ])
    if len(linhas) == 1:
        linhas.append(["(plano de amostragem não gerado)", "", "", "", "", ""])
    tabela = Table(linhas, colWidths=[6.2 * cm, 2.2 * cm, 1.8 * cm, 2.0 * cm, 1.4 * cm, 3.6 * cm], repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRINCIPAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, r in enumerate(dados["regras"], start=1):
        if r["status"] == "deficit":
            estilo.append(("TEXTCOLOR", (5, i), (5, i), COR_ALERTA))
        elif r["status"] == "ok":
            estilo.append(("TEXTCOLOR", (5, i), (5, i), COR_OK))
    tabela.setStyle(TableStyle(estilo))
    elementos.append(tabela)
    elementos.append(Paragraph("Recoletas não entram no mínimo (Art. 44 §2). \"Em andamento\" = período ainda não encerrado.", peq))

    # Padrão bacteriológico da rede
    rede = dados["rede"]
    elementos.append(Paragraph("Padrão bacteriológico na rede (mês)", h2))
    elementos.append(Paragraph(
        f"Amostras analisadas: {rede['amostras_analisadas']} — com coliformes totais: {rede['com_coliformes_totais']} — "
        f"com E. coli: {rede['com_e_coli']}. Situação: <b>{rede['status'].upper()}</b>.", normal))
    for t in rede["textos"]:
        elementos.append(Paragraph(f"• {t}", peq))

    if dados["recoletas_pendentes"]:
        elementos.append(Paragraph("Recoletas pendentes", h2))
        for r in dados["recoletas_pendentes"]:
            elementos.append(Paragraph(
                f"• {r['codigo']} ({r['posicao']}) prevista para {r['data_prevista']}{' — ATRASADA' if r['atrasada'] else ''}", peq))

    # Amostras do mês
    elementos.append(Paragraph("Amostras coletadas no mês", h2))
    linhas = [["Código", "Data", "Ponto", "Grupo", "Coliformes", "E. coli"]]
    for a in amostras:
        e = _sim_nao(a["e_coli"]) if a["e_coli_nmp"] is None else f"{a['e_coli_nmp']:g} NMP"
        linhas.append([a["codigo"] or "", a["data"], Paragraph(a["ponto"] + (" (recoleta)" if a["recoleta"] else ""), peq),
                       Paragraph(GRUPO_LABEL.get(a["grupo"], a["grupo"]), peq), _sim_nao(a["coliformes"]), e])
    if len(linhas) == 1:
        linhas.append(["—", "", "", "", "", ""])
    tabela = Table(linhas, colWidths=[2.8 * cm, 3.0 * cm, 4.2 * cm, 3.6 * cm, 1.9 * cm, 1.7 * cm], repeatRows=1)
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COR_PRINCIPAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D0D5DD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabela)

    if dados.get("ecoli_captacao_media_geometrica_12m") is not None:
        elementos.append(Paragraph(
            f"Média geométrica de E. coli na captação (12 meses): {dados['ecoli_captacao_media_geometrica_12m']} NMP/100 mL "
            "(limite de atenção: 1.000).", peq))

    elementos.append(Spacer(1, 0.6 * cm))
    elementos.append(Paragraph(
        "Resultados do laboratório próprio (kit/estufa) são de controle operacional. A conformidade formal depende do laboratório "
        "e dos métodos atenderem à Portaria 888/2021 (boas práticas e ISO/IEC 17025 — Arts. 20 a 22). Documento gerado pelo SIGA; "
        "revisar antes de encaminhar à Vigilância Sanitária.", peq))

    doc.build(elementos)
    return buffer.getvalue()
