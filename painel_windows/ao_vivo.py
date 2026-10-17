"""Acompanhamento ao vivo das análises da ETA (químico).

O painel consulta /analise-eta/ao-vivo a cada 15 s (AreaQuimico faz o agendamento) e entrega aqui só o que é novo:
a aba "Ao vivo" mostra a situação de cada ETA e os últimos lançamentos; a faixa de alertas fica visível em todas as
abas enquanto houver análise fora do padrão da Portaria 888/2021 ou análise atrasada (mais de 2h20 sem coleta).
"""
import json
from datetime import datetime

import customtkinter as ctk

import tema

INTERVALO_MS = 15000
SEGUNDOS_NOVA = 120  # quanto tempo um lançamento recém-chegado fica com a etiqueta "NOVA"
MAX_EVENTOS = 60
LOCALIDADE_LABEL = {"sede": "Chalé (sede)", "penha_do_coco": "Penha do Coco", "bananal": "Bananal", "agua_limpa": "Água Limpa"}
CAMPOS = [("turbidez_filtrada", "Turb. filtrada"), ("turbidez_tratada", "Turb. tratada"), ("ph_tratada", "pH"),
          ("cloro_residual", "Cloro residual"), ("cor_tratada", "Cor")]


def duracao_texto(minutos):
    """135 -> '2h15'; 42 -> '42 min'."""
    if minutos is None:
        return "—"
    return f"{minutos // 60}h{minutos % 60:02d}" if minutos >= 60 else f"{minutos} min"


def hora_br(texto_iso):
    try:
        return datetime.fromisoformat(texto_iso).strftime("%H:%M")
    except (TypeError, ValueError):
        return "—"


def lista_alertas(texto):
    if not texto:
        return []
    try:
        v = json.loads(texto)
        return v if isinstance(v, list) else [str(v)]
    except ValueError:
        return [texto]


def alertas_de(localidades):
    """Situação atual -> [(chave, texto, nivel)]. A chave não muda enquanto o mesmo problema persiste
    (assim o aviso sonoro só toca quando surge um problema novo)."""
    saida = []
    for l in localidades:
        nome = LOCALIDADE_LABEL.get(l["localidade"], l["localidade"])
        if l.get("ultima_conforme") is False:
            motivo = (l.get("ultimos_alertas") or ["parâmetro fora do padrão"])[0]
            saida.append((f"fora:{l['localidade']}:{l['ultima_coleta']}",
                          f"{nome}: análise das {hora_br(l['ultima_coleta'])} fora do padrão — {motivo}", "erro"))
        if l.get("atrasada"):
            saida.append((f"atraso:{l['localidade']}:{l.get('ultima_coleta')}",
                          f"{nome}: sem análise há {duracao_texto(l['minutos_desde_ultima'])} "
                          f"(atrasada em {duracao_texto(l['minutos_atraso'])})", "atraso"))
    return saida


class FaixaAlertas(ctk.CTkFrame):
    """Faixa vermelha/âmbar no topo da Área do Químico. Some quando não há alertas."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._conteudo = None

    def mostrar(self, alertas):
        for w in self.winfo_children():
            w.destroy()
        if not alertas:
            self.pack_forget()
            return
        for _chave, texto, nivel in alertas:
            erro = nivel == "erro"
            linha = ctk.CTkFrame(self, fg_color=tema.ERRO_FUNDO if erro else tema.AMBAR_FUNDO, corner_radius=8)
            linha.pack(fill="x", pady=2)
            ctk.CTkLabel(linha, text=("⚠  " if erro else "⏱  ") + texto, anchor="w", justify="left", wraplength=1050,
                         text_color=tema.ERRO if erro else tema.AMBAR, font=ctk.CTkFont(size=12, weight="bold")
                         ).pack(fill="x", padx=12, pady=6)


class AbaAoVivo(ctk.CTkScrollableFrame):
    """Cartões por localidade + últimos lançamentos (análises e lavagens), do mais novo para o mais antigo."""

    def __init__(self, master, api=None):
        super().__init__(master, fg_color="transparent")
        self.eventos = []  # dicts {tipo, dados, recebido}
        self.localidades = []
        self.ultima_verificacao = None
        self.erro = None
        self.cabecalho = ctk.CTkLabel(self, text="Conectando…", anchor="w", text_color=tema.TEXTO_SUAVE)
        self.cabecalho.pack(fill="x", pady=(0, 8))
        self.grade = ctk.CTkFrame(self, fg_color="transparent")
        self.grade.pack(fill="x")
        for c in range(4):
            self.grade.columnconfigure(c, weight=1, uniform="vivo")
        self.titulo_feed = ctk.CTkLabel(self, text="Últimos lançamentos dos operadores de ETA", anchor="w",
                                        font=ctk.CTkFont(size=14, weight="bold"), text_color=tema.AZUL_ESCURO)
        self.titulo_feed.pack(fill="x", pady=(18, 6))
        self.feed = ctk.CTkFrame(self, fg_color="transparent")
        self.feed.pack(fill="x")

    def definir_contexto(self, localidade, mes):  # esta aba mostra todas as localidades, sempre
        pass

    # --- dados -------------------------------------------------------------
    def receber(self, dados):
        """Recebe a resposta de /ao-vivo. Devolve (qtd_analises_novas, qtd_fora_do_padrao_novas)."""
        agora = datetime.now()
        primeira = dados.get("primeira_carga", False)
        novos = [{"tipo": "analise", "dados": a, "recebido": agora, "nova": not primeira} for a in dados["analises"]]
        novos += [{"tipo": "lavagem", "dados": l, "recebido": agora, "nova": not primeira} for l in dados["lavagens"]]
        self.eventos = (novos + self.eventos)[:MAX_EVENTOS]
        self.eventos.sort(key=lambda e: e["dados"].get("coletado_em") or e["dados"].get("hora") or "", reverse=True)
        self.localidades = dados["localidades"]
        self.ultima_verificacao, self.erro = agora, None
        self._desenhar()
        analises_novas = [e for e in novos if e["tipo"] == "analise" and not primeira]
        return len(analises_novas), sum(1 for e in analises_novas if e["dados"].get("conforme") is False)

    def falhou(self, mensagem):
        self.erro = mensagem
        self._cabecalho()

    # --- desenho -----------------------------------------------------------
    def _cabecalho(self):
        if self.erro:
            self.cabecalho.configure(text=f"●  Sem conexão com o servidor — tentando de novo em 15 s.  ({self.erro})",
                                     text_color=tema.ERRO)
        elif self.ultima_verificacao:
            self.cabecalho.configure(
                text=f"●  Ao vivo — atualiza sozinho a cada 15 s  ·  última verificação às {self.ultima_verificacao:%H:%M:%S}",
                text_color=tema.OK)

    def _desenhar(self):
        self._cabecalho()
        for w in self.grade.winfo_children():
            w.destroy()
        for i, l in enumerate(self.localidades):
            self._cartao(i, l)
        for w in self.feed.winfo_children():
            w.destroy()
        if not self.eventos:
            ctk.CTkLabel(self.feed, text="Nenhum lançamento ainda. Quando um operador de ETA registrar uma análise, ela aparece aqui.",
                         text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=12)
        agora = datetime.now()
        for e in self.eventos:
            nova = e["nova"] and (agora - e["recebido"]).total_seconds() < SEGUNDOS_NOVA
            (self._linha_analise if e["tipo"] == "analise" else self._linha_lavagem)(e["dados"], nova)

    def _cartao(self, coluna, l):
        if not l["tem_dados"]:
            texto, cor, fundo = "Sem dados", tema.TEXTO_SUAVE, tema.AZUL_CLARO
        elif l["ultima_conforme"] is False:
            texto, cor, fundo = "Fora do padrão", tema.ERRO, tema.ERRO_FUNDO
        elif l["atrasada"]:
            texto, cor, fundo = "Análise atrasada", tema.AMBAR, tema.AMBAR_FUNDO
        else:
            texto, cor, fundo = "Conforme", tema.OK, tema.OK_FUNDO
        c = ctk.CTkFrame(self.grade, fg_color=tema.BRANCO, border_color=tema.LINHA, border_width=1, corner_radius=12)
        c.grid(row=0, column=coluna, sticky="nsew", padx=5, pady=4)
        ctk.CTkLabel(c, text=LOCALIDADE_LABEL.get(l["localidade"], l["localidade"]), font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=tema.TEXTO).pack(pady=(14, 6), padx=10)
        ctk.CTkLabel(c, text=texto, text_color=cor, fg_color=fundo, corner_radius=12,
                     font=ctk.CTkFont(size=11, weight="bold"), padx=10, pady=2).pack()
        if l["tem_dados"]:
            ctk.CTkLabel(c, text=f"Última análise às {hora_br(l['ultima_coleta'])}\n(há {duracao_texto(l['minutos_desde_ultima'])})",
                         text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=11), justify="center").pack(pady=(8, 2), padx=8)
            if l["atrasada"]:
                ctk.CTkLabel(c, text=f"Atrasada em {duracao_texto(l['minutos_atraso'])}", text_color=tema.AMBAR,
                             font=ctk.CTkFont(size=11, weight="bold")).pack()
        else:
            ctk.CTkLabel(c, text="Nenhuma análise registrada", text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=11)
                         ).pack(pady=(8, 2))
        if not l.get("no_turno", True):
            ctk.CTkLabel(c, text="fora do turno", text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=10)).pack()
        ctk.CTkFrame(c, height=1, fg_color="transparent").pack(pady=6)

    def _linha_analise(self, a, nova):
        fora = a.get("conforme") is False
        linha = ctk.CTkFrame(self.feed, fg_color=tema.ERRO_FUNDO if fora else "#F6F8FB", corner_radius=8)
        linha.pack(fill="x", pady=3)
        cab = ctk.CTkFrame(linha, fg_color="transparent")
        cab.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(cab, text=f"{LOCALIDADE_LABEL.get(a['localidade'], a['localidade'])}  ·  {hora_br(a['coletado_em'])}",
                     font=ctk.CTkFont(weight="bold"), text_color=tema.TEXTO).pack(side="left")
        if nova:
            ctk.CTkLabel(cab, text="NOVA", text_color=tema.BRANCO, fg_color=tema.DESTAQUE, corner_radius=8,
                         font=ctk.CTkFont(size=10, weight="bold"), padx=8).pack(side="left", padx=8)
        ctk.CTkLabel(cab, text="Fora do padrão" if fora else "Conforme", text_color=tema.ERRO if fora else tema.OK,
                     font=ctk.CTkFont(weight="bold")).pack(side="right")
        partes = [f"{rot}: {a[k]}" for k, rot in CAMPOS if a.get(k) is not None]
        ctk.CTkLabel(linha, text="   ·   ".join(partes) or "—", anchor="w", text_color=tema.TEXTO_SUAVE
                     ).pack(fill="x", padx=12, pady=(2, 8 if not fora else 2))
        if fora:
            ctk.CTkLabel(linha, text="\n".join(f"• {x}" for x in lista_alertas(a.get("alertas"))), anchor="w", justify="left",
                         text_color=tema.ERRO, wraplength=900).pack(fill="x", padx=12, pady=(0, 8))
        if a.get("observacoes"):
            ctk.CTkLabel(linha, text=f"Obs.: {a['observacoes']}", anchor="w", text_color=tema.TEXTO_SUAVE, wraplength=900,
                         justify="left").pack(fill="x", padx=12, pady=(0, 8))

    def _linha_lavagem(self, l, nova):
        linha = ctk.CTkFrame(self.feed, fg_color="#F6F8FB", corner_radius=8)
        linha.pack(fill="x", pady=3)
        cab = ctk.CTkFrame(linha, fg_color="transparent")
        cab.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(cab, text=f"{LOCALIDADE_LABEL.get(l['localidade'], l['localidade'])}  ·  {hora_br(l['hora'])}",
                     font=ctk.CTkFont(weight="bold"), text_color=tema.TEXTO).pack(side="left")
        if nova:
            ctk.CTkLabel(cab, text="NOVA", text_color=tema.BRANCO, fg_color=tema.DESTAQUE, corner_radius=8,
                         font=ctk.CTkFont(size=10, weight="bold"), padx=8).pack(side="left", padx=8)
        detalhe = []
        if l.get("tempo_gasto_min") is not None:
            detalhe.append(f"{l['tempo_gasto_min']:g} min")
        if l.get("volume_gasto") is not None:
            detalhe.append(f"volume gasto {l['volume_gasto']:g}")
        ctk.CTkLabel(cab, text="Lavagem de filtro" + (" — " + " · ".join(detalhe) if detalhe else ""),
                     text_color=tema.TEXTO_SUAVE).pack(side="right")
