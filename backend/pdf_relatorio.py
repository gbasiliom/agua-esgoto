import io
import os
import json
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable,
)

COR_PRINCIPAL = colors.HexColor("#0891b2")

TIPO_LABEL = {
    "vazamento": "Vazamento", "manutencao": "Manutenção",
    "religacao": "Religação", "vistoria": "Vistoria", "outro": "Outro",
}
STATUS_LABEL = {
    "aberto": "Aberto", "atribuido": "Atribuído", "em_andamento": "Em andamento",
    "concluido": "Concluído", "cancelado": "Cancelado",
}


def _formatar_data(dt):
    return dt.strftime("%d/%m/%Y às %H:%M") if dt else "—"


def gerar_pdf_chamado(chamado, cliente, tecnico, fotos):
    """Gera o PDF do relatório de atendimento e retorna os bytes prontos."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )

    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle(
        "TituloRelatorio", parent=estilos["Title"], textColor=COR_PRINCIPAL, alignment=TA_CENTER,
    )
    estilo_subtitulo = ParagraphStyle(
        "Subtitulo", parent=estilos["Normal"], alignment=TA_CENTER, textColor=colors.grey,
    )
    estilo_secao = ParagraphStyle(
        "Secao", parent=estilos["Heading2"], textColor=COR_PRINCIPAL, spaceBefore=14, spaceAfter=6,
    )
    estilo_normal = estilos["Normal"]

    elementos = []

    elementos.append(Paragraph("💧 Sistema de Água e Esgoto", estilo_titulo))
    elementos.append(Paragraph(f"Relatório de Atendimento — Chamado #{chamado.id}", estilo_subtitulo))
    elementos.append(Spacer(1, 12))
    elementos.append(HRFlowable(width="100%", color=COR_PRINCIPAL, thickness=1))
    elementos.append(Spacer(1, 12))

    # --- Dados do cliente ---
    elementos.append(Paragraph("Dados do cliente", estilo_secao))
    dados_cliente = [
        ["Nome:", cliente.nome if cliente else "—"],
        ["Endereço:", cliente.endereco if cliente else "—"],
        ["Bairro / Cidade:", f"{cliente.bairro or '—'} / {cliente.cidade or '—'}" if cliente else "—"],
        ["Hidrômetro:", cliente.hidrometro if cliente else "—"],
    ]
    tabela_cliente = Table(dados_cliente, colWidths=[4 * cm, 12 * cm])
    tabela_cliente.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabela_cliente)

    # --- Dados do chamado ---
    elementos.append(Paragraph("Dados do chamado", estilo_secao))
    dados_chamado = [
        ["Tipo:", TIPO_LABEL.get(chamado.tipo, chamado.tipo)],
        ["Prioridade:", chamado.prioridade],
        ["Status:", STATUS_LABEL.get(chamado.status, chamado.status)],
        ["Técnico responsável:", tecnico.nome if tecnico else "—"],
        ["Aberto em:", _formatar_data(chamado.abertura)],
        ["Atribuído em:", _formatar_data(chamado.atribuicao)],
        ["Concluído em:", _formatar_data(chamado.conclusao)],
    ]
    tabela_chamado = Table(dados_chamado, colWidths=[4 * cm, 12 * cm])
    tabela_chamado.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(tabela_chamado)

    # --- Descrições ---
    elementos.append(Paragraph("Problema relatado pelo cliente", estilo_secao))
    elementos.append(Paragraph(chamado.descricao_problema or "—", estilo_normal))

    elementos.append(Paragraph("Solução aplicada pelo técnico", estilo_secao))
    elementos.append(Paragraph(chamado.descricao_solucao or "Chamado ainda não foi fechado.", estilo_normal))

    # --- Checklist da situação encontrada ---
    if chamado.checklist:
        try:
            itens_checklist = json.loads(chamado.checklist)
        except (json.JSONDecodeError, TypeError):
            itens_checklist = None

        if itens_checklist:
            # Só mostra o que foi de fato marcado pelo técnico — itens não
            # marcados não aparecem no relatório final.
            itens_marcados = [descricao for descricao, marcado in itens_checklist.items() if marcado]

            if itens_marcados:
                elementos.append(Paragraph("Checklist da situação encontrada", estilo_secao))
                linhas_checklist = [["[x]", descricao] for descricao in itens_marcados]
                tabela_checklist = Table(linhas_checklist, colWidths=[1 * cm, 15 * cm])
                tabela_checklist.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                elementos.append(tabela_checklist)

    # --- Materiais utilizados ---
    if chamado.materiais_utilizados:
        elementos.append(Paragraph("Materiais utilizados", estilo_secao))
        elementos.append(Paragraph(chamado.materiais_utilizados, estilo_normal))

    # --- Fotos ---
    if fotos:
        elementos.append(Paragraph("Fotos do atendimento", estilo_secao))
        for foto in fotos:
            caminho_absoluto = foto.caminho_arquivo
            if os.path.exists(caminho_absoluto):
                try:
                    img = Image(caminho_absoluto, width=10 * cm, height=7.5 * cm, kind="proportional")
                    elementos.append(img)
                    elementos.append(Spacer(1, 8))
                except Exception:
                    elementos.append(Paragraph(f"(Não foi possível carregar: {caminho_absoluto})", estilo_normal))

    elementos.append(Spacer(1, 20))
    elementos.append(HRFlowable(width="100%", color=colors.grey, thickness=0.5))
    elementos.append(Paragraph(
        "Relatório gerado automaticamente pelo Sistema de Água e Esgoto — A'Guilda",
        ParagraphStyle("Rodape", parent=estilos["Normal"], textColor=colors.grey, fontSize=8, alignment=TA_CENTER),
    ))

    doc.build(elementos)
    buffer.seek(0)
    return buffer.read()
