"""Resumo do painel administrativo: poucos números que importam, a lista do que depende do administrador
hoje e uma tabela pequena por localidade. Sem frases de efeito, atalhos repetidos ou rodapé.

Regra do SAAE: só a SEDE tem hidrômetro — leitura, fatura e "em aberto" existem apenas na sede.
"""
from datetime import date, datetime

import customtkinter as ctk

import tema
from async_helper import rodar_em_background

LOCALIDADES = [("sede", "Sede"), ("penha_do_coco", "Penha do Coco"), ("bananal", "Bananal"), ("agua_limpa", "Água Limpa")]
ABERTOS = ("aberto", "atribuido", "em_andamento")


def _reais(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _data(texto):
    try:
        return datetime.fromisoformat(str(texto)[:19]).date()
    except Exception:
        return None


class Indicador(ctk.CTkFrame):
    """Quadro com rótulo pequeno, número grande e uma linha de apoio. Clicável."""

    def __init__(self, master, rotulo, comando):
        super().__init__(master, fg_color=tema.BRANCO, border_color=tema.LINHA, border_width=1, corner_radius=12,
                         cursor="hand2")
        self.rot = ctk.CTkLabel(self, text=rotulo.upper(), font=ctk.CTkFont(size=10, weight="bold"),
                                text_color=tema.TEXTO_SUAVE, anchor="w")
        self.rot.pack(fill="x", padx=16, pady=(14, 0))
        self.valor = ctk.CTkLabel(self, text="…", font=ctk.CTkFont(size=24, weight="bold"), text_color=tema.AZUL_ESCURO,
                                  anchor="w")
        self.valor.pack(fill="x", padx=16, pady=(2, 0))
        self.apoio = ctk.CTkLabel(self, text=" ", font=ctk.CTkFont(size=11), text_color=tema.TEXTO_SUAVE, anchor="w")
        self.apoio.pack(fill="x", padx=16, pady=(0, 14))
        for w in (self, self.rot, self.valor, self.apoio):
            w.bind("<Button-1>", lambda _e: comando())

    def definir(self, valor, apoio, tom="normal"):
        cor = {"ruim": tema.ERRO, "bom": tema.OK}.get(tom, tema.TEXTO_SUAVE)
        self.valor.configure(text=valor)
        self.apoio.configure(text=apoio, text_color=cor)


class TelaResumo(ctk.CTkScrollableFrame):
    def __init__(self, master, api, ir_para):
        super().__init__(master, fg_color=tema.FUNDO)
        self.api = api
        self.ir_para = ir_para  # ir_para("Faturamento", "Faturas")
        self.columnconfigure(0, weight=1)

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 12))
        ctk.CTkLabel(topo, text="Resumo", font=ctk.CTkFont(size=21, weight="bold"), text_color=tema.AZUL_ESCURO).pack(side="left")
        self.hora = ctk.CTkLabel(topo, text="Carregando…", font=ctk.CTkFont(size=12), text_color=tema.TEXTO_SUAVE)
        self.hora.pack(side="right")

        grade = ctk.CTkFrame(self, fg_color="transparent")
        grade.grid(row=1, column=0, sticky="ew", padx=18)
        self.ind = {}
        defs = [
            ("faturas", "Faturas em aberto (Sede)", lambda: self.ir_para("Faturamento", "Faturas")),
            ("leituras", "Leituras do mês (Sede)", lambda: self.ir_para("Faturamento", "Leituras")),
            ("cadastros", "Cadastros para aprovar", lambda: self.ir_para("Clientes")),
            ("pagar", "Contas a pagar (7 dias)", lambda: self.ir_para("Financeiro")),
        ]
        for i, (chave, rotulo, cmd) in enumerate(defs):
            grade.columnconfigure(i, weight=1, uniform="ind")
            c = Indicador(grade, rotulo, cmd)
            c.grid(row=0, column=i, sticky="nsew", padx=6, pady=6)
            self.ind[chave] = c

        meio = ctk.CTkFrame(self, fg_color="transparent")
        meio.grid(row=2, column=0, sticky="ew", padx=18, pady=(10, 20))
        meio.columnconfigure(0, weight=3, uniform="m")
        meio.columnconfigure(1, weight=2, uniform="m")

        self.cartao_atencao = self._cartao(meio, "Precisa da sua atenção")
        self.cartao_atencao.grid(row=0, column=0, sticky="nsew", padx=6)
        self.corpo_atencao = ctk.CTkFrame(self.cartao_atencao, fg_color="transparent")
        self.corpo_atencao.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(self.corpo_atencao, text="Carregando…", text_color=tema.TEXTO_SUAVE).pack(anchor="w", pady=6)

        self.cartao_loc = self._cartao(meio, "Por localidade")
        self.cartao_loc.grid(row=0, column=1, sticky="nsew", padx=6)
        self.corpo_loc = ctk.CTkFrame(self.cartao_loc, fg_color="transparent")
        self.corpo_loc.pack(fill="x", padx=16, pady=(0, 12))

        self.carregar()

    @staticmethod
    def _cartao(master, titulo):
        c = ctk.CTkFrame(master, fg_color=tema.BRANCO, border_color=tema.LINHA, border_width=1, corner_radius=12)
        ctk.CTkLabel(c, text=titulo.upper(), font=ctk.CTkFont(size=11, weight="bold"), text_color=tema.TEXTO_SUAVE,
                     anchor="w").pack(fill="x", padx=16, pady=(14, 8))
        return c

    # ------------------------------------------------------------------ dados
    def carregar(self):
        api = self.api

        def tentar(fn, *a):
            try:
                return fn(*a)
            except Exception:
                return None

        def buscar():
            return {
                "faturas": tentar(api.listar_faturas, "aberto"),
                "contas": tentar(api.listar_contas_pagar, "aberto"),
                "solicitacoes": tentar(api.listar_solicitacoes, "pendente"),
                "clientes": tentar(api.listar_clientes),
                "leituras": tentar(api.listar_leituras),
                "chamados": tentar(api.listar_chamados),
                "licitacoes": tentar(api.listar_licitacoes, "publicada"),
                "usuarios": tentar(api.listar_usuarios) if api.tipo_usuario == "admin" else None,
            }

        rodar_em_background(self, buscar, self._mostrar, lambda _e: None)

    def _mostrar(self, d):
        if not self.winfo_exists():
            return
        hoje = date.today()
        competencia = f"{hoje.year:04d}-{hoje.month:02d}"
        self.hora.configure(text=f"Atualizado {datetime.now():%H:%M} · {hoje:%d/%m/%Y}")

        # --- faturas (só existem na sede)
        faturas = d["faturas"]
        if faturas is None:
            self.ind["faturas"].definir("—", "indisponível")
        else:
            total = sum(float(f["valor_total"]) for f in faturas)
            vencidas = [f for f in faturas if (_data(f["vencimento"]) or hoje) < hoje]
            self.ind["faturas"].definir(_reais(total), f"{len(faturas)} faturas · {len(vencidas)} vencidas",
                                        "ruim" if vencidas else "normal")

        # --- clientes / leituras
        clientes = d["clientes"]
        sede = [c for c in (clientes or []) if c.get("localidade") in (None, "sede")]
        leituras = d["leituras"]
        if leituras is None or clientes is None:
            self.ind["leituras"].definir("—", "indisponível")
            leituras_mes, pend_leit = [], []
        else:
            leituras_mes = [x for x in leituras if x.get("competencia") == competencia]
            pend_leit = [x for x in leituras if x.get("status") == "pendente"]
            faltam = max(0, len(sede) - len(leituras_mes))
            self.ind["leituras"].definir(f"{len(leituras_mes)} / {len(sede)}", f"{faltam} ainda não enviadas")
        cad_pend = [c for c in (clientes or []) if c.get("status_cadastro") == "pendente"]
        if clientes is None:
            self.ind["cadastros"].definir("—", "indisponível")
        else:
            self.ind["cadastros"].definir(str(len(cad_pend)), "moradores aguardando" if cad_pend else "nenhum pendente")

        # --- contas a pagar
        contas = d["contas"]
        venc_contas = []
        if contas is None:
            self.ind["pagar"].definir("—", "indisponível")
        else:
            prox = [c for c in contas if (_data(c["vencimento"]) or hoje).toordinal() <= hoje.toordinal() + 7]
            venc_contas = [c for c in contas if (_data(c["vencimento"]) or hoje) < hoje]
            self.ind["pagar"].definir(_reais(sum(float(c["valor"]) for c in prox)),
                                      f"{len(prox)} contas · {len(venc_contas)} vencida(s)",
                                      "ruim" if venc_contas else "normal")

        # --- lista de atenção
        itens = []
        if venc_contas:
            itens.append(("e", f"{len(venc_contas)} conta(s) a pagar vencida(s)",
                          f"Total {_reais(sum(float(c['valor']) for c in venc_contas))}", "Abrir", lambda: self.ir_para("Financeiro")))
        sol = d["solicitacoes"] or []
        if sol:
            itens.append(("a", f"{len(sol)} solicitação(ões) de material aguardando aprovação", "Pedidos dos técnicos", "Aprovar",
                          lambda: self.ir_para("Operação", "Solicitações")))
        if cad_pend:
            itens.append(("a", f"{len(cad_pend)} morador(es) pedindo aprovação de cadastro", "", "Revisar", lambda: self.ir_para("Clientes")))
        if pend_leit:
            itens.append(("a", f"{len(pend_leit)} leitura(s) de hidrômetro para conferir", "Somente Sede", "Conferir",
                          lambda: self.ir_para("Faturamento", "Leituras")))
        proximas = []
        for lic in d["licitacoes"] or []:
            dt = _data(lic.get("data_abertura"))
            if dt and 0 <= (dt - hoje).days <= 7:
                proximas.append((dt, lic))
        for dt, lic in sorted(proximas, key=lambda x: x[0])[:2]:
            itens.append(("i", f"Licitação {lic.get('numero_processo') or ''} abre em {(dt - hoje).days} dia(s)".replace("  ", " "),
                          (lic.get("objeto") or "")[:70], "Ver", lambda: self.ir_para("Licitações")))
        trocas = [u for u in (d["usuarios"] or []) if u.get("trocar_senha")]
        bloq = [u for u in (d["usuarios"] or []) if u.get("bloqueado")]
        if bloq:
            itens.append(("e", f"{len(bloq)} conta(s) bloqueada(s) por tentativas erradas", "Resete a senha se for engano", "Ver",
                          lambda: self.ir_para("Segurança", "Acessos")))
        if trocas:
            itens.append(("i", f"{len(trocas)} conta(s) com troca de senha pendente", "Ainda não entraram com a senha nova", "Ver",
                          lambda: self.ir_para("Segurança", "Acessos")))

        for w in self.corpo_atencao.winfo_children():
            w.destroy()
        if not itens:
            ctk.CTkLabel(self.corpo_atencao, text="✔  Nada pendente com você agora.", text_color=tema.OK,
                         font=ctk.CTkFont(size=13)).pack(anchor="w", pady=8)
        cores = {"e": tema.ERRO, "a": tema.AMBAR, "i": tema.DESTAQUE}
        for i, (tom, titulo, apoio, botao, cmd) in enumerate(itens):
            if i:
                ctk.CTkFrame(self.corpo_atencao, height=1, fg_color="#EDF1F6").pack(fill="x")
            linha = ctk.CTkFrame(self.corpo_atencao, fg_color="transparent")
            linha.pack(fill="x", pady=7)
            ctk.CTkLabel(linha, text="●", text_color=cores[tom], font=ctk.CTkFont(size=12), width=18).pack(side="left")
            bloco = ctk.CTkFrame(linha, fg_color="transparent")
            bloco.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(bloco, text=titulo, anchor="w", font=ctk.CTkFont(size=13), text_color=tema.TEXTO).pack(fill="x")
            if apoio:
                ctk.CTkLabel(bloco, text=apoio, anchor="w", font=ctk.CTkFont(size=11), text_color=tema.TEXTO_SUAVE).pack(fill="x")
            ctk.CTkButton(linha, text=botao, width=84, height=28, fg_color="white", text_color=tema.AZUL, border_width=1,
                          border_color=tema.AZUL, hover_color=tema.AZUL_CLARO, command=cmd).pack(side="right")

        # --- por localidade
        for w in self.corpo_loc.winfo_children():
            w.destroy()
        cab = ctk.CTkFrame(self.corpo_loc, fg_color="transparent")
        cab.pack(fill="x")
        for texto, larg, ancora in (("LOCAL", 110, "w"), ("CHAMADOS", 80, "e"), ("MORADORES", 80, "e")):
            ctk.CTkLabel(cab, text=texto, width=larg, anchor=ancora, font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=tema.TEXTO_SUAVE).pack(side="left" if ancora == "w" else "right")
        chamados = d["chamados"] or []
        for chave, nome in LOCALIDADES:
            moradores = len([c for c in (clientes or []) if (c.get("localidade") or "sede") == chave])
            abertos = len([x for x in chamados if x.get("local_atendimento") == chave and x.get("status") in ABERTOS])
            linha = ctk.CTkFrame(self.corpo_loc, fg_color="transparent")
            linha.pack(fill="x")
            ctk.CTkFrame(linha, height=1, fg_color="#EDF1F6").pack(fill="x")
            ln = ctk.CTkFrame(linha, fg_color="transparent")
            ln.pack(fill="x", pady=6)
            ctk.CTkLabel(ln, text=nome, width=110, anchor="w", font=ctk.CTkFont(size=13), text_color=tema.TEXTO).pack(side="left")
            ctk.CTkLabel(ln, text=str(abertos), width=80, anchor="e", font=ctk.CTkFont(size=13),
                         text_color=tema.AMBAR if abertos else tema.TEXTO).pack(side="right")
            ctk.CTkLabel(ln, text=str(moradores) if clientes is not None else "—", width=80, anchor="e",
                         font=ctk.CTkFont(size=13), text_color=tema.TEXTO).pack(side="right")
        ctk.CTkLabel(self.corpo_loc, text="Hidrômetro, leitura e fatura: somente Sede.", anchor="w",
                     font=ctk.CTkFont(size=10), text_color=tema.TEXTO_SUAVE).pack(fill="x", pady=(8, 0))
