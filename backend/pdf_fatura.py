import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

COR_PRINCIPAL = colors.HexColor("#0891b2")


def _formatar_data(dt):
    return dt.strftime("%d/%m/%Y") if dt else "—"


def _formatar_competencia(competencia):
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    ano, mes = competencia.split("-")
    return f"{meses[int(mes) - 1]}/{ano}"


def gerar_pdf_fatura(fatura, cliente):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("Titulo", parent=estilos["Title"], textColor=COR_PRINCIPAL, alignment=TA_CENTER)
    estilo_subtitulo = ParagraphStyle("Subtitulo", parent=estilos["Normal"], alignment=TA_CENTER, textColor=colors.grey)
    estilo_secao = ParagraphStyle("Secao", parent=estilos["Heading2"], textColor=COR_PRINCIPAL, spaceBefore=14, spaceAfter=6)
    estilo_valor_grande = ParagraphStyle(
        "ValorGrande", parent=estilos["Normal"], fontSize=28, alignment=TA_CENTER,
        textColor=COR_PRINCIPAL, spaceBefore=10, spaceAfter=10,
    )

    elementos = []
    elementos.append(Paragraph("💧 SIGA", estilo_titulo))
    elementos.append(Paragraph(f"Conta de Água e Esgoto — {_formatar_competencia(fatura.competencia)}", estilo_subtitulo))
    elementos.append(Spacer(1, 12))
    elementos.append(HRFlowable(width="100%", color=COR_PRINCIPAL, thickness=1))
    elementos.append(Spacer(1, 12))

    elementos.append(Paragraph("Dados do cliente", estilo_secao))
    dados_cliente = [
        ["Nome:", cliente.nome if cliente else "—"],
        ["Endereço:", cliente.endereco if cliente else "—"],
        ["Hidrômetro:", cliente.hidrometro if cliente else "—"],
    ]
    tabela_cliente = Table(dados_cliente, colWidths=[4 * cm, 12 * cm])
    tabela_cliente.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabela_cliente)

    elementos.append(Paragraph("Detalhes do consumo", estilo_secao))
    dados_consumo = [
        ["Consumo no mês:", f"{fatura.consumo_m3:.0f} m³"],
        ["Valor da água:", f"R$ {fatura.valor_agua:.2f}"],
        ["Valor do esgoto:", f"R$ {fatura.valor_esgoto:.2f}"],
        ["Vencimento:", _formatar_data(fatura.vencimento)],
        ["Status:", "Pago" if fatura.status == "pago" else ("Vencido" if fatura.status == "vencido" else "Em aberto")],
    ]
    tabela_consumo = Table(dados_consumo, colWidths=[4 * cm, 12 * cm])
    tabela_consumo.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabela_consumo)

    elementos.append(Spacer(1, 10))
    elementos.append(Paragraph("Valor total a pagar", estilo_secao))
    elementos.append(Paragraph(f"R$ {fatura.valor_total:.2f}", estilo_valor_grande))

    elementos.append(Spacer(1, 20))
    elementos.append(HRFlowable(width="100%", color=colors.grey, thickness=0.5))
    elementos.append(Paragraph(
        "Este documento é a conta de água e esgoto — não é um boleto bancário registrado. "
        "Consulte a prefeitura sobre as formas de pagamento disponíveis.",
        ParagraphStyle("Rodape", parent=estilos["Normal"], textColor=colors.grey, fontSize=8, alignment=TA_CENTER),
    ))

    doc.build(elementos)
    buffer.seek(0)
    return buffer.read()
