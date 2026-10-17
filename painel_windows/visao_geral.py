"""Visão Geral do painel SIGA (estilo Acordes de Davi): aviso com faixa lateral, título em duas cores,
cartões por localidade (chamados em aberto) e atalhos das áreas. Não traz dados do químico.
"""
from datetime import date
import customtkinter as ctk

import tema
from async_helper import rodar_em_background

LOCALIDADES = [
    ("sede", "Sede"),
    ("penha_do_coco", "Penha do Coco"),
    ("bananal", "Bananal"),
    ("agua_limpa", "Água Limpa"),
]


ABERTOS = ("aberto", "atribuido", "em_andamento")


class Cartao(ctk.CTkFrame):
    """Cartão branco com borda fina, ícone, título, texto e rodapé (etiqueta ou link)."""

    def __init__(self, master, icone, titulo, texto="", comando=None):
        super().__init__(master, fg_color=tema.BRANCO, border_color=tema.LINHA, border_width=1, corner_radius=12)
        self.icone_lbl = ctk.CTkLabel(
            self, text=icone, width=34, height=34, corner_radius=17, fg_color=tema.AZUL_CLARO,
            text_color=tema.AZUL, font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.icone_lbl.pack(pady=(16, 6))
        self.titulo_lbl = ctk.CTkLabel(
            self, text=titulo, font=ctk.CTkFont(size=14, weight="bold"), text_color=tema.TEXTO,
        )
        self.titulo_lbl.pack(padx=10)
        self.texto_lbl = ctk.CTkLabel(
            self, text=texto, font=ctk.CTkFont(size=11), text_color=tema.TEXTO_SUAVE, wraplength=210,
            justify="center",
        )
        self.texto_lbl.pack(padx=10, pady=(2, 8))
        self.rodape = ctk.CTkFrame(self, fg_color="transparent")
        self.rodape.pack(pady=(0, 14))
        if comando:
            for w in (self, self.icone_lbl, self.titulo_lbl, self.texto_lbl, self.rodape):
                w.bind("<Button-1>", lambda _e: comando())
                w.configure(cursor="hand2")

    def etiqueta(self, texto, cor, fundo):
        for w in self.rodape.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.rodape, text=texto, text_color=cor, fg_color=fundo, corner_radius=12,
            font=ctk.CTkFont(size=11, weight="bold"), padx=10, pady=2,
        ).pack()

    def link(self, texto):
        for w in self.rodape.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.rodape, text=texto, text_color=tema.AZUL, font=ctk.CTkFont(size=11, weight="bold", underline=True),
        ).pack()


class TelaVisaoGeral(ctk.CTkScrollableFrame):
    def __init__(self, master, api, ir_para):
        super().__init__(master, fg_color=tema.FUNDO)
        self.api = api
        self.ir_para = ir_para  # ir_para("Operação", "Chamados")
        self.columnconfigure(0, weight=1)

        aviso = ctk.CTkFrame(self, fg_color=tema.BRANCO, corner_radius=10)
        aviso.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 0))
        ctk.CTkFrame(aviso, width=4, height=1, fg_color=tema.DESTAQUE, corner_radius=2).pack(side="left", fill="y")
        corpo = ctk.CTkFrame(aviso, fg_color="transparent")
        corpo.pack(side="left", fill="both", expand=True, padx=16, pady=12)
        ctk.CTkLabel(
            corpo, text="Água é vida: cuidar dela é cuidar de cada família de Chalé.",
            font=ctk.CTkFont(size=13, slant="italic"), text_color=tema.TEXTO_SUAVE,
        ).pack()
        self.aviso_info = ctk.CTkLabel(
            corpo, text="SAAE DE CHALÉ · " + date.today().strftime("%d/%m/%Y"),
            font=ctk.CTkFont(size=10, weight="bold"), text_color=tema.AZUL,
        )
        self.aviso_info.pack(pady=(4, 0))

        hero = ctk.CTkFrame(self, fg_color="transparent")
        hero.grid(row=1, column=0, pady=(20, 6))
        titulo = ctk.CTkFrame(hero, fg_color="transparent")
        titulo.pack()
        ctk.CTkLabel(titulo, text="Sistema ", font=ctk.CTkFont(size=26, weight="bold"), text_color=tema.TEXTO).pack(side="left")
        ctk.CTkLabel(titulo, text="Integrado de Gestão", font=ctk.CTkFont(size=26, weight="bold"), text_color=tema.DESTAQUE).pack(side="left")
        ctk.CTkLabel(
            hero, text="Acompanhe cada localidade, aprove solicitações e controle chamados, estoque e faturamento em um só lugar.",
            text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=13),
        ).pack(pady=(6, 10))
        self.resumo_chamados = ctk.CTkLabel(hero, text="", text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=12))
        self.resumo_chamados.pack()

        ctk.CTkLabel(
            self, text="Localidades", font=ctk.CTkFont(size=13, weight="bold"), text_color=tema.TEXTO,
        ).grid(row=2, column=0, sticky="w", padx=24, pady=(14, 6))
        grade_loc = ctk.CTkFrame(self, fg_color="transparent")
        grade_loc.grid(row=3, column=0, sticky="ew", padx=24)
        self.cartoes_loc = {}
        for i, (chave, nome) in enumerate(LOCALIDADES):
            grade_loc.columnconfigure(i, weight=1, uniform="loc")
            c = Cartao(grade_loc, "◎", nome, "Carregando…",
                       comando=lambda: self.ir_para("Operação", "Chamados"))
            c.grid(row=0, column=i, sticky="nsew", padx=6, pady=6)
            self.cartoes_loc[chave] = c

        ctk.CTkLabel(
            self, text="Áreas", font=ctk.CTkFont(size=13, weight="bold"), text_color=tema.TEXTO,
        ).grid(row=4, column=0, sticky="w", padx=24, pady=(14, 6))
        grade_mod = ctk.CTkFrame(self, fg_color="transparent")
        grade_mod.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 20))
        modulos = [
            ("▤", "Estoque", "Materiais e movimentações", "Operação", "Estoque"),
            ("☎", "Chamados", "Vazamentos, esgoto e faltas de água", "Operação", "Chamados"),
            ("✉", "Solicitações", "Pedidos de material dos técnicos", "Operação", "Solicitações"),
            ("$", "Faturamento", "Leituras, tarifas e faturas", "Comercial", "Faturamento"),
        ]
        for i, (ic, nome, txt, grupo, item) in enumerate(modulos):
            grade_mod.columnconfigure(i, weight=1, uniform="mod")
            c = Cartao(grade_mod, ic, nome, txt, comando=lambda g=grupo, it=item: self.ir_para(g, it))
            c.link("Abrir")
            c.grid(row=0, column=i, sticky="nsew", padx=6, pady=6)

        self.carregar()

    def carregar(self):
        def buscar():
            try:
                chamados = self.api.listar_chamados()
            except Exception:
                chamados = None
            try:
                resumo = self.api.relatorio_resumo()
            except Exception:
                resumo = None
            return chamados, resumo

        def sucesso(dados):
            chamados, resumo = dados
            if not self.winfo_exists():
                return
            for chave, c in self.cartoes_loc.items():
                if chamados is None:
                    c.texto_lbl.configure(text="Sem dados de chamados")
                    c.etiqueta("Indisponível", tema.TEXTO_SUAVE, tema.AZUL_CLARO)
                    continue
                abertos = [x for x in chamados if x.get("local_atendimento") == chave and x.get("status") in ABERTOS]
                if abertos:
                    c.texto_lbl.configure(text=f"{len(abertos)} chamado(s) em aberto")
                    c.etiqueta(f"⚠ {len(abertos)} em aberto", tema.AMBAR, tema.AMBAR_FUNDO)
                else:
                    c.texto_lbl.configure(text="Nenhum chamado em aberto")
                    c.etiqueta("✔ Sem pendências", tema.OK, tema.OK_FUNDO)
            if resumo:
                self.resumo_chamados.configure(
                    text=f"Chamados em aberto: {resumo['chamados_em_aberto']}   ·   "
                         f"concluídos: {resumo['chamados_concluidos']}"
                )

        rodar_em_background(self, buscar, sucesso, lambda _e: None)
