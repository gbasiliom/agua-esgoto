"""Área do Químico do painel — tudo o que é da parte química/laboratorial do sistema.

Conformidade com a Portaria GM/MS 888/2021, análises diárias da ETA, coletas e
resultados, laudos e cadastro de pontos/regras.
Todas as chamadas à API rodam em segundo plano (a janela não trava).
"""
import json
import os
from datetime import date, datetime

import customtkinter as ctk
from tkinter import messagebox, filedialog

import tema
from api_client import ApiClient, ApiError
from async_helper import rodar_em_background
from ao_vivo import AbaAoVivo, FaixaAlertas, alertas_de, INTERVALO_MS

LOCALIDADE_LABEL = {
    "sede": "Chalé (sede)",
    "penha_do_coco": "Penha do Coco",
    "bananal": "Bananal",
    "agua_limpa": "Água Limpa",
}
PERIODO_LABEL = {"dia": "Diária", "semana": "Semanal", "mes": "Mensal", "trimestre": "Trimestral", "semestre": "Semestral"}
PONTO_TIPO_LABEL = {"captacao": "Captação", "saida_eta": "Saída da ETA", "reservatorio": "Reservatório", "rede": "Rede"}
STATUS_AMOSTRA_LABEL = {
    "pendente": "Pendente", "coletada": "Coletada", "analisada": "Analisada",
    "encaminhada": "Encaminhada ao laboratório", "laudo_recebido": "Laudo recebido", "cancelada": "Cancelada",
}
TIPO_LAUDO_LABEL = {
    "agua_bruta_semestral": "Água bruta (semestral)", "bacteriologico": "Bacteriológico", "outro": "Outro",
}
SITUACAO = {  # status da regra -> (texto, cor, fundo)
    "ok": ("Cumprido", tema.OK, tema.OK_FUNDO),
    "em_andamento": ("Em andamento", tema.AMBAR, tema.AMBAR_FUNDO),
    "deficit": ("Déficit", tema.ERRO, tema.ERRO_FUNDO),
}
REDE_SITUACAO = {
    "ok": ("Conforme", tema.OK), "atencao": ("Atenção", tema.AMBAR),
    "violacao": ("Fora do padrão", tema.ERRO), "sem_dados": ("Sem dados", tema.TEXTO_SUAVE),
}

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _msg_erro(e, padrao):
    return str(e) if isinstance(e, ApiError) else padrao


def _data_br(texto_iso):
    if not texto_iso:
        return "—"
    try:
        return datetime.fromisoformat(texto_iso).strftime("%d/%m/%Y")
    except ValueError:
        return texto_iso


def _data_hora_br(texto_iso):
    if not texto_iso:
        return "—"
    try:
        return datetime.fromisoformat(texto_iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return texto_iso


def _parse_data_br(texto):
    """'25/10/2026' -> '2026-10-25'. Vazio -> None. Inválido -> ValueError."""
    texto = (texto or "").strip()
    if not texto:
        return None
    return datetime.strptime(texto, "%d/%m/%Y").date().isoformat()


def _limpar(frame):
    for w in frame.winfo_children():
        w.destroy()


def _titulo_secao(master, texto):
    ctk.CTkLabel(
        master, text=texto, font=ctk.CTkFont(size=14, weight="bold"), text_color=tema.AZUL_ESCURO, anchor="w"
    ).pack(fill="x", pady=(18, 6))


def _botao(master, texto, comando, principal=False, largura=120, **kw):
    if principal:
        return ctk.CTkButton(master, text=texto, width=largura, fg_color=tema.AZUL, hover_color=tema.AZUL_HOVER,
                             command=comando, **kw)
    return ctk.CTkButton(master, text=texto, width=largura, fg_color=tema.BRANCO, hover_color=tema.AZUL_CLARO,
                         text_color=tema.TEXTO, border_width=1, border_color=tema.LINHA, command=comando, **kw)


def _etiqueta(master, texto, cor, fundo):
    return ctk.CTkLabel(master, text=texto, text_color=cor, fg_color=fundo, corner_radius=10,
                        font=ctk.CTkFont(size=12), padx=10, pady=1)


def _meses_disponiveis(quantidade=12):
    """Lista [(rótulo, 'AAAA-MM')] do mês atual para trás."""
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    saida = []
    for _ in range(quantidade):
        saida.append((f"{MESES[mes - 1].capitalize()} / {ano}", f"{ano:04d}-{mes:02d}"))
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return saida


class _AbaBase(ctk.CTkScrollableFrame):
    """Aba que sabe se recarregar para (localidade, mês)."""

    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api
        self.localidade = None
        self.mes = None
        self._geracao = 0  # descarta respostas de pedidos antigos (troca rápida de localidade/mês)

    def definir_contexto(self, localidade, mes):
        self.localidade, self.mes = localidade, mes
        self.carregar()

    def _pedido(self, funcao, sucesso, erro_padrao):
        """Roda `funcao` em segundo plano e só aplica o resultado se o contexto não mudou."""
        self._geracao += 1
        minha = self._geracao

        def ok(resultado):
            if minha == self._geracao and self.winfo_exists():
                sucesso(resultado)

        def falha(e):
            if minha == self._geracao and self.winfo_exists():
                _limpar(self)
                ctk.CTkLabel(self, text=_msg_erro(e, erro_padrao), text_color=tema.ERRO).pack(pady=20, anchor="w")

        rodar_em_background(self, funcao, ok, falha)

    def _carregando(self):
        _limpar(self)
        ctk.CTkLabel(self, text="Carregando...", text_color=tema.TEXTO_SUAVE).pack(pady=20, anchor="w")

    def carregar(self):  # pragma: no cover — implementado nas abas
        raise NotImplementedError


# ----------------------------------------------------------------------------
# 1) Conformidade
# ----------------------------------------------------------------------------
class AbaConformidade(_AbaBase):
    def carregar(self):
        self._carregando()
        loc, mes = self.localidade, self.mes
        self._pedido(lambda: self.api.qualidade_conformidade(loc, mes), self._desenhar,
                     "Falha ao carregar a conformidade")

    def _cartao(self, master, coluna, titulo, valor, subtitulo, cor_valor=None, cor_sub=None):
        c = ctk.CTkFrame(master, fg_color=tema.BRANCO, border_width=1, border_color=tema.LINHA, corner_radius=8)
        c.grid(row=0, column=coluna, sticky="nsew", padx=5)
        ctk.CTkLabel(c, text=titulo, text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=12), anchor="w",
                     wraplength=200, justify="left").pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(c, text=valor, text_color=cor_valor or tema.AZUL_ESCURO,
                     font=ctk.CTkFont(size=22, weight="bold"), anchor="w").pack(fill="x", padx=14)
        ctk.CTkLabel(c, text=subtitulo, text_color=cor_sub or tema.TEXTO_SUAVE, font=ctk.CTkFont(size=12),
                     anchor="w", wraplength=200, justify="left").pack(fill="x", padx=14, pady=(0, 10))

    def _desenhar(self, d):
        _limpar(self)
        regras = d["regras"]
        if not regras:
            ctk.CTkLabel(
                self, anchor="w", justify="left", text_color=tema.AMBAR, wraplength=700,
                text="O plano de amostragem desta localidade ainda não foi gerado.\n"
                     "Vá em \"Pontos e regras\", informe a população e gere o plano mínimo da norma.",
            ).pack(fill="x", pady=20)
            return

        exigido = sum(r["exigido"] for r in regras)
        realizado = sum(r["realizado"] for r in regras)
        pct = 100.0 * realizado / exigido if exigido else 100.0
        em_andamento = sum(1 for r in regras if r["status"] == "em_andamento")
        deficit = sum(1 for r in regras if r["status"] == "deficit")
        if deficit:
            sub1, cor1 = f"{deficit} item(ns) em déficit", tema.ERRO
        elif em_andamento:
            sub1, cor1 = f"{em_andamento} item(ns) em andamento", tema.AMBAR
        else:
            sub1, cor1 = "Tudo cumprido até agora", tema.OK

        rede = d["rede"]
        texto_rede, cor_rede = REDE_SITUACAO.get(rede["status"], (rede["status"], tema.TEXTO))
        sub_rede = f"{rede['amostras_analisadas']} amostras · {rede['com_e_coli']} com E. coli · {rede['com_coliformes_totais']} com colif. totais"

        rec = d["recoletas_pendentes"]
        atrasadas = sum(1 for r in rec if r["atrasada"])
        gm = d.get("ecoli_captacao_media_geometrica_12m")

        cartoes = ctk.CTkFrame(self, fg_color="transparent")
        cartoes.pack(fill="x")
        for i in range(4):
            cartoes.grid_columnconfigure(i, weight=1, uniform="c")
        self._cartao(cartoes, 0, "Plano do mês cumprido", f"{pct:.0f}%", sub1, cor_sub=cor1)
        self._cartao(cartoes, 1, "Rede (coliformes e E. coli)", texto_rede, sub_rede, cor_valor=cor_rede)
        self._cartao(cartoes, 2, "Recoletas pendentes", str(len(rec)),
                     f"{atrasadas} atrasada(s) (Art. 27)" if atrasadas else "Nenhuma atrasada",
                     cor_valor=tema.ERRO if atrasadas else None, cor_sub=tema.ERRO if atrasadas else tema.OK)
        if gm is None:
            self._cartao(cartoes, 3, "E. coli na captação (média geom. 12 meses)", "—", "Sem análises ainda")
        else:
            acima = gm >= 1000
            self._cartao(cartoes, 3, "E. coli na captação (média geom. 12 meses)", f"{gm:.0f}",
                         "≥ 1.000: reforçar monitoramento" if acima else "abaixo de 1.000",
                         cor_sub=tema.ERRO if acima else tema.OK)

        for texto in d.get("alertas", []):
            self._faixa(texto, tema.ERRO, tema.ERRO_FUNDO)
        for texto in rede.get("textos", []):
            if rede["status"] != "ok":
                self._faixa(texto, tema.AMBAR, tema.AMBAR_FUNDO)

        _titulo_secao(self, "Exigido × realizado no mês")
        self._tabela(regras)

        if rec:
            _titulo_secao(self, "Recoletas pendentes")
            for r in rec:
                linha = ctk.CTkFrame(self, fg_color=tema.ERRO_FUNDO if r["atrasada"] else tema.AMBAR_FUNDO, corner_radius=6)
                linha.pack(fill="x", pady=2)
                prev = _data_br(r["data_prevista"])
                ctk.CTkLabel(
                    linha, anchor="w",
                    text=f"{r.get('codigo') or '#' + str(r['amostra_id'])} · posição: {r.get('posicao') or '—'} · prevista {prev}"
                         + ("  — ATRASADA" if r["atrasada"] else ""),
                    text_color=tema.ERRO if r["atrasada"] else tema.AMBAR,
                ).pack(fill="x", padx=12, pady=6)

        notas = [r["nota"] for r in regras if r.get("nota")]
        for n in notas:
            ctk.CTkLabel(self, text=n, text_color=tema.TEXTO_SUAVE, anchor="w", wraplength=760,
                         justify="left").pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(
            self, anchor="w", justify="left", wraplength=760, text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=11),
            text=f"Referência: Portaria GM/MS nº 888/2021 (a regulamentação estadual de MG não foi localizada). "
                 f"População abastecida considerada: {d['populacao_abastecida']:,}".replace(",", ".") + ".",
        ).pack(fill="x", pady=(14, 0))

    def _faixa(self, texto, cor, fundo):
        f = ctk.CTkFrame(self, fg_color=fundo, corner_radius=6)
        f.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(f, text=texto, text_color=cor, anchor="w", justify="left", wraplength=760).pack(
            fill="x", padx=12, pady=8)

    def _tabela(self, regras):
        tab = ctk.CTkFrame(self, fg_color="transparent")
        tab.pack(fill="x")
        larguras = [(3, "Parâmetro"), (1, "Onde"), (1, "Frequência"), (2, "Realizado"), (1, "Situação")]
        for i, (peso, titulo) in enumerate(larguras):
            tab.grid_columnconfigure(i, weight=peso, uniform=f"t{i}")
            ctk.CTkLabel(tab, text=titulo, fg_color=tema.AZUL_CLARO, text_color=tema.TEXTO_SUAVE,
                         font=ctk.CTkFont(size=12, weight="bold"), anchor="w", padx=10, height=30
                         ).grid(row=0, column=i, sticky="nsew")
        for n, r in enumerate(regras, start=1):
            texto_sit, cor, fundo = SITUACAO.get(r["status"], (r["status"], tema.TEXTO, tema.BRANCO))
            ctk.CTkLabel(tab, text=r["descricao"], anchor="w", justify="left", wraplength=250,
                         text_color=tema.TEXTO).grid(row=n, column=0, sticky="w", padx=10, pady=7)
            ctk.CTkLabel(tab, text=PONTO_TIPO_LABEL.get(r["ponto_tipo"], r["ponto_tipo"]), anchor="w",
                         text_color=tema.TEXTO).grid(row=n, column=1, sticky="w", padx=10)
            ctk.CTkLabel(tab, text=PERIODO_LABEL.get(r["periodo"], r["periodo"]) + f" ×{r['quantidade_por_periodo']}",
                         anchor="w", text_color=tema.TEXTO).grid(row=n, column=2, sticky="w", padx=10)
            bloco = ctk.CTkFrame(tab, fg_color="transparent")
            bloco.grid(row=n, column=3, sticky="w", padx=10)
            barra = ctk.CTkProgressBar(bloco, width=110, height=7, progress_color=cor, fg_color="#E7ECF3")
            barra.set(min(1.0, (r["realizado"] / r["exigido"]) if r["exigido"] else 1.0))
            barra.pack(side="left")
            ctk.CTkLabel(bloco, text=f" {r['realizado']} / {r['exigido']}", text_color=tema.TEXTO).pack(side="left")
            _etiqueta(tab, texto_sit, cor, fundo).grid(row=n, column=4, sticky="w", padx=10)
            ctk.CTkFrame(tab, height=1, fg_color="#EDF0F4").grid(row=n + 0, column=0, columnspan=5, sticky="sew")



# ----------------------------------------------------------------------------
# 2) Análises da ETA (lançadas de 2 em 2 horas pelo operador de ETA)
# ----------------------------------------------------------------------------
class AbaAnalisesEta(_AbaBase):
    def __init__(self, master, api):
        super().__init__(master, api)
        self.so_fora = False

    def carregar(self):
        self._carregando()
        loc, so_fora = self.localidade, self.so_fora
        self._pedido(lambda: self.api.listar_analises_eta(so_fora, loc), self._desenhar,
                     "Falha ao carregar as análises da ETA")

    def _alternar(self):
        self.so_fora = not self.so_fora
        self.carregar()

    def _desenhar(self, analises):
        _limpar(self)
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(barra, text="Leituras do operador de ETA (turbidez, pH, cloro, cor)", text_color=tema.TEXTO_SUAVE
                     ).pack(side="left")
        _botao(barra, "Mostrar todas" if self.so_fora else "Só fora do padrão", self._alternar, largura=150).pack(side="right")
        if not analises:
            ctk.CTkLabel(self, text="Nenhuma análise fora do padrão." if self.so_fora else "Nenhuma análise registrada nesta localidade.",
                         text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=20)
            return
        for a in analises[:300]:
            fora = a.get("conforme") is False
            linha = ctk.CTkFrame(self, fg_color=tema.ERRO_FUNDO if fora else "#F6F8FB", corner_radius=8)
            linha.pack(fill="x", pady=3)
            cab = ctk.CTkFrame(linha, fg_color="transparent")
            cab.pack(fill="x", padx=12, pady=(8, 0))
            ctk.CTkLabel(cab, text=_data_hora_br(a["coletado_em"]), font=ctk.CTkFont(weight="bold"),
                         text_color=tema.TEXTO).pack(side="left")
            ctk.CTkLabel(cab, text="Fora do padrão" if fora else "Conforme", text_color=tema.ERRO if fora else tema.OK,
                         font=ctk.CTkFont(weight="bold")).pack(side="right")
            campos = [("turbidez_filtrada", "Turb. filtrada"), ("turbidez_tratada", "Turb. tratada"),
                      ("ph_tratada", "pH"), ("cloro_residual", "Cloro residual"), ("cor_tratada", "Cor")]
            partes = [f"{rot}: {a[k]}" for k, rot in campos if a.get(k) is not None]
            ctk.CTkLabel(linha, text="   ·   ".join(partes) or "—", anchor="w", text_color=tema.TEXTO_SUAVE
                         ).pack(fill="x", padx=12, pady=(2, 8 if not (fora and a.get("alertas")) else 2))
            if fora and a.get("alertas"):
                try:
                    alertas = json.loads(a["alertas"])
                except ValueError:
                    alertas = [a["alertas"]]
                ctk.CTkLabel(linha, text="\n".join(f"• {x}" for x in alertas), anchor="w", justify="left",
                             text_color=tema.ERRO, wraplength=700).pack(fill="x", padx=12, pady=(0, 8))

# ----------------------------------------------------------------------------
# 3) Coletas e resultados
# ----------------------------------------------------------------------------
class JanelaResultado(ctk.CTkToplevel):
    def __init__(self, master, api, amostra, nome_ponto):
        super().__init__(master)
        self.title(f"Resultado — {amostra.get('codigo') or '#' + str(amostra['id'])}")
        self.geometry("460x520")
        self.configure(fg_color=tema.BRANCO)
        self.api = api
        self.corpo = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.corpo.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(self.corpo, text=f"{nome_ponto}", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x")
        self.cabecalho = [
            ("Grupo", amostra["grupo"]), ("Coleta", _data_hora_br(amostra.get("coletado_em"))),
            ("Status", STATUS_AMOSTRA_LABEL.get(amostra["status"], amostra["status"])),
            ("Cloro residual (mg/L)", amostra.get("cloro_residual")), ("Turbidez (uT)", amostra.get("turbidez")),
            ("pH", amostra.get("ph")), ("Cor aparente (uH)", amostra.get("cor_aparente")),
        ]
        for rot, val in self.cabecalho:
            if val not in (None, ""):
                self._linha(rot, val)
        ctk.CTkLabel(self.corpo, text="Carregando resultado bacteriológico...", text_color=tema.TEXTO_SUAVE).pack(pady=10)
        rodar_em_background(self, lambda: api.qualidade_ver_resultado(amostra["id"]), self._ok, self._sem_resultado)

    def _linha(self, rotulo, valor):
        l = ctk.CTkFrame(self.corpo, fg_color="transparent")
        l.pack(fill="x", pady=1)
        ctk.CTkLabel(l, text=rotulo, text_color=tema.TEXTO_SUAVE, anchor="w", width=170).pack(side="left")
        ctk.CTkLabel(l, text=str(valor), text_color=tema.TEXTO, anchor="w", wraplength=240,
                     justify="left").pack(side="left", fill="x")

    @staticmethod
    def _sn(v):
        return "—" if v is None else ("Presente" if v else "Ausente")

    def _sem_resultado(self, e):
        self.corpo.winfo_children()[-1].configure(text="Resultado bacteriológico ainda não lançado.")

    def _ok(self, r):
        self.corpo.winfo_children()[-1].destroy()
        ctk.CTkLabel(self.corpo, text="Resultado bacteriológico", font=ctk.CTkFont(weight="bold"),
                     text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x", pady=(12, 4))
        self._linha("Coliformes totais", self._sn(r.get("coliformes_totais_presente")))
        self._linha("E. coli", self._sn(r.get("e_coli_presente")))
        if r.get("e_coli_nmp") is not None:
            self._linha("E. coli (NMP/100 mL)", r["e_coli_nmp"])
        if r.get("cianobacterias_cel_ml") is not None:
            self._linha("Cianobactérias (cél/mL)", r["cianobacterias_cel_ml"])
        self._linha("Método", r.get("metodo") or "—")
        self._linha("Lote / validade do kit", f"{r.get('lote_kit') or '—'} / {_data_br(r.get('validade_kit'))}")
        if r.get("incubacao_temp_c") is not None:
            self._linha("Incubação", f"{r['incubacao_temp_c']} °C · {_data_hora_br(r.get('incubacao_inicio'))} → {_data_hora_br(r.get('incubacao_fim'))}")
        conforme = r.get("conforme")
        if conforme is not None:
            self._linha("Situação", "Conforme" if conforme else "FORA DO PADRÃO")
        if r.get("alertas"):
            self._linha("Alertas", r["alertas"])
        if r.get("observacoes"):
            self._linha("Observações", r["observacoes"])


class AbaColetas(_AbaBase):
    def __init__(self, master, api):
        super().__init__(master, api)
        self.filtro = "Todos"

    def carregar(self):
        self._carregando()
        loc, mes = self.localidade, self.mes
        status = None if self.filtro == "Todos" else next(
            (k for k, v in STATUS_AMOSTRA_LABEL.items() if v == self.filtro), None)

        def buscar():
            return self.api.qualidade_listar_amostras(loc, mes, status), self.api.qualidade_listar_pontos(loc)

        self._pedido(buscar, self._desenhar, "Falha ao carregar as coletas")

    def _mudar_filtro(self, valor):
        self.filtro = valor
        self.carregar()

    def _desenhar(self, resultado):
        amostras, pontos = resultado
        nomes = {p["id"]: p["nome"] for p in pontos}
        _limpar(self)
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(barra, text="Situação:", text_color=tema.TEXTO_SUAVE).pack(side="left", padx=(0, 6))
        menu = ctk.CTkOptionMenu(
            barra, values=["Todos"] + list(STATUS_AMOSTRA_LABEL.values()), width=210, command=self._mudar_filtro,
            fg_color=tema.BRANCO, button_color=tema.AZUL, button_hover_color=tema.AZUL_HOVER,
            text_color=tema.TEXTO, dropdown_text_color=tema.TEXTO,
        )
        menu.set(self.filtro)
        menu.pack(side="left")
        ctk.CTkLabel(barra, text=f"{len(amostras)} amostra(s) no mês", text_color=tema.TEXTO_SUAVE).pack(side="right")

        if not amostras:
            ctk.CTkLabel(self, text="Nenhuma amostra encontrada neste mês.", text_color=tema.TEXTO_SUAVE,
                         anchor="w").pack(fill="x", pady=20)
            return
        for a in amostras:
            nome = nomes.get(a["ponto_id"], f"Ponto #{a['ponto_id']}")
            recoleta = a.get("recoleta_de_id") is not None
            linha = ctk.CTkFrame(self, fg_color="#F6F8FB" if not recoleta else tema.AMBAR_FUNDO, corner_radius=8)
            linha.pack(fill="x", pady=3)
            data = _data_hora_br(a.get("coletado_em")) if a.get("coletado_em") else f"prevista {_data_br(a.get('data_prevista'))}"
            titulo = f"{a.get('codigo') or '#' + str(a['id'])} · {nome}" + ("  (recoleta)" if recoleta else "")
            ctk.CTkLabel(linha, text=titulo, anchor="w", font=ctk.CTkFont(weight="bold"),
                         text_color=tema.TEXTO).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
            fq = []
            if a.get("cloro_residual") is not None:
                fq.append(f"cloro {a['cloro_residual']}")
            if a.get("turbidez") is not None:
                fq.append(f"turb. {a['turbidez']}")
            if a.get("ph") is not None:
                fq.append(f"pH {a['ph']}")
            detalhe = f"{data} · {STATUS_AMOSTRA_LABEL.get(a['status'], a['status'])}" + (" · " + ", ".join(fq) if fq else "")
            ctk.CTkLabel(linha, text=detalhe, anchor="w", text_color=tema.TEXTO_SUAVE).grid(
                row=1, column=0, sticky="w", padx=12, pady=(0, 8))
            linha.grid_columnconfigure(0, weight=1)
            _botao(linha, "Ver detalhes", lambda a=a, n=nome: JanelaResultado(self, self.api, a, n), largura=100
                   ).grid(row=0, column=1, rowspan=2, padx=12)


# ----------------------------------------------------------------------------
# 4) Laudos
# ----------------------------------------------------------------------------
class JanelaNovoLaudo(ctk.CTkToplevel):
    def __init__(self, master, api, localidade, ao_salvar):
        super().__init__(master)
        self.title("Registrar laudo de laboratório")
        self.geometry("460x600")
        self.configure(fg_color=tema.BRANCO)
        self.api, self.localidade, self.ao_salvar = api, localidade, ao_salvar
        self.arquivo = None
        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=20, pady=16)
        ctk.CTkLabel(corpo, text=f"Laudo — {LOCALIDADE_LABEL.get(localidade, localidade)}",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x")

        self.tipo = ctk.CTkOptionMenu(corpo, values=list(TIPO_LAUDO_LABEL.values()), fg_color=tema.BRANCO,
                                      button_color=tema.AZUL, text_color=tema.TEXTO, dropdown_text_color=tema.TEXTO)
        self._rotulo(corpo, "Tipo de laudo"); self.tipo.pack(fill="x")
        self.laboratorio = self._campo(corpo, "Laboratório *")
        self.numero = self._campo(corpo, "Nº do laudo")
        self.data_coleta = self._campo(corpo, "Data da coleta * (DD/MM/AAAA)")
        self.data_emissao = self._campo(corpo, "Data de emissão (DD/MM/AAAA)")
        self._rotulo(corpo, "Resultado geral")
        self.conforme = ctk.CTkOptionMenu(corpo, values=["Não informado", "Conforme", "Fora do padrão"],
                                          fg_color=tema.BRANCO, button_color=tema.AZUL, text_color=tema.TEXTO,
                                          dropdown_text_color=tema.TEXTO)
        self.conforme.pack(fill="x")
        self.resumo = self._campo(corpo, "Resumo dos parâmetros")
        linha = ctk.CTkFrame(corpo, fg_color="transparent")
        linha.pack(fill="x", pady=(12, 0))
        _botao(linha, "Anexar PDF/foto...", self._escolher_arquivo, largura=150).pack(side="left")
        self.lbl_arquivo = ctk.CTkLabel(linha, text="Nenhum arquivo", text_color=tema.TEXTO_SUAVE)
        self.lbl_arquivo.pack(side="left", padx=10)
        self.botao = _botao(corpo, "Registrar laudo", self.salvar, principal=True, largura=160)
        self.botao.pack(pady=18)

    def _rotulo(self, master, texto):
        ctk.CTkLabel(master, text=texto, text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=(10, 2))

    def _campo(self, master, rotulo):
        self._rotulo(master, rotulo)
        e = ctk.CTkEntry(master, border_color=tema.LINHA)
        e.pack(fill="x")
        return e

    def _escolher_arquivo(self):
        c = filedialog.askopenfilename(filetypes=[("Laudo", "*.pdf *.jpg *.jpeg *.png")], parent=self)
        if c:
            self.arquivo = c
            self.lbl_arquivo.configure(text=os.path.basename(c))

    def salvar(self):
        try:
            coleta = _parse_data_br(self.data_coleta.get())
            emissao = _parse_data_br(self.data_emissao.get())
        except ValueError:
            messagebox.showwarning("Data inválida", "Use o formato DD/MM/AAAA (ex.: 25/10/2026).", parent=self)
            return
        if not self.laboratorio.get().strip() or not coleta:
            messagebox.showwarning("Faltou informação", "Informe o laboratório e a data da coleta.", parent=self)
            return
        tipo = next(k for k, v in TIPO_LAUDO_LABEL.items() if v == self.tipo.get())
        conforme = {"Conforme": "true", "Fora do padrão": "false"}.get(self.conforme.get())
        dados = {
            "localidade": self.localidade, "tipo": tipo, "laboratorio": self.laboratorio.get().strip(),
            "numero_laudo": self.numero.get().strip(), "data_coleta": coleta, "data_emissao": emissao,
            "parametros_resumo": self.resumo.get().strip(), "conforme": conforme,
        }
        self.botao.configure(state="disabled", text="Enviando...")

        def erro(e):
            self.botao.configure(state="normal", text="Registrar laudo")
            messagebox.showerror("Erro", _msg_erro(e, "Falha ao registrar o laudo"), parent=self)

        def ok(_):
            self.ao_salvar()
            self.destroy()

        rodar_em_background(self, lambda: self.api.qualidade_registrar_laudo(dados, self.arquivo), ok, erro)


class AbaLaudos(_AbaBase):
    def carregar(self):
        self._carregando()
        loc = self.localidade
        self._pedido(lambda: self.api.qualidade_listar_laudos(loc), self._desenhar, "Falha ao carregar os laudos")

    def _desenhar(self, laudos):
        _limpar(self)
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(barra, text="Laudos de laboratório (análise semestral de água bruta, bacteriológicos e outros)",
                     text_color=tema.TEXTO_SUAVE, anchor="w").pack(side="left")
        if self.api.tipo_usuario in ("admin", "quimico"):
            _botao(barra, "+ Registrar laudo", lambda: JanelaNovoLaudo(self, self.api, self.localidade, self.carregar),
                   principal=True, largura=140).pack(side="right")
        if not laudos:
            ctk.CTkLabel(self, text="Nenhum laudo registrado para esta localidade.", text_color=tema.TEXTO_SUAVE,
                         anchor="w").pack(fill="x", pady=20)
            return
        for l in laudos:
            linha = ctk.CTkFrame(self, fg_color="#F6F8FB", corner_radius=8)
            linha.pack(fill="x", pady=3)
            linha.grid_columnconfigure(0, weight=1)
            titulo = f"{TIPO_LAUDO_LABEL.get(l['tipo'], l['tipo'])} · {l['laboratorio']}" + (
                f" · nº {l['numero_laudo']}" if l.get("numero_laudo") else "")
            ctk.CTkLabel(linha, text=titulo, anchor="w", font=ctk.CTkFont(weight="bold"), text_color=tema.TEXTO
                         ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 0))
            detalhe = f"Coleta {_data_br(l['data_coleta'])}"
            if l.get("data_emissao"):
                detalhe += f" · emitido {_data_br(l['data_emissao'])}"
            if l.get("parametros_resumo"):
                detalhe += f" · {l['parametros_resumo']}"
            ctk.CTkLabel(linha, text=detalhe, anchor="w", text_color=tema.TEXTO_SUAVE, wraplength=520, justify="left"
                         ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))
            c = l.get("conforme")
            if c is not None:
                _etiqueta(linha, "Conforme" if c else "Fora do padrão", tema.OK if c else tema.ERRO,
                          tema.OK_FUNDO if c else tema.ERRO_FUNDO).grid(row=0, column=1, rowspan=2, padx=6)
            if l.get("tem_arquivo"):
                _botao(linha, "Abrir arquivo", lambda l=l: self._baixar(l), largura=100).grid(
                    row=0, column=2, rowspan=2, padx=12)

    def _baixar(self, laudo):
        def sucesso(conteudo):
            ext = ".pdf" if conteudo[:4] == b"%PDF" else (".png" if conteudo[:4] == b"\x89PNG" else ".jpg")
            caminho = filedialog.asksaveasfilename(
                defaultextension=ext, initialfile=f"laudo-{laudo.get('numero_laudo') or laudo['id']}{ext}")
            if not caminho:
                return
            with open(caminho, "wb") as f:
                f.write(conteudo)
            try:
                os.startfile(caminho)
            except Exception:
                messagebox.showinfo("Salvo", f"Laudo salvo em: {caminho}")

        rodar_em_background(self, lambda: self.api.qualidade_baixar_laudo(laudo["id"]), sucesso,
                            lambda e: messagebox.showerror("Erro", _msg_erro(e, "Falha ao baixar o laudo")))


# ----------------------------------------------------------------------------
# 5) Pontos e regras
# ----------------------------------------------------------------------------
class JanelaNovoPonto(ctk.CTkToplevel):
    def __init__(self, master, api, localidade, ao_salvar):
        super().__init__(master)
        self.title("Novo ponto de coleta")
        self.geometry("400x420")
        self.configure(fg_color=tema.BRANCO)
        self.api, self.localidade, self.ao_salvar = api, localidade, ao_salvar
        c = ctk.CTkFrame(self, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=20, pady=16)
        ctk.CTkLabel(c, text="Tipo", text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=(0, 2))
        self.tipo = ctk.CTkOptionMenu(c, values=list(PONTO_TIPO_LABEL.values()), fg_color=tema.BRANCO,
                                      button_color=tema.AZUL, text_color=tema.TEXTO, dropdown_text_color=tema.TEXTO)
        self.tipo.pack(fill="x")
        ctk.CTkLabel(c, text="Nome *", text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=(10, 2))
        self.nome = ctk.CTkEntry(c, border_color=tema.LINHA); self.nome.pack(fill="x")
        ctk.CTkLabel(c, text="Descrição / endereço", text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=(10, 2))
        self.desc = ctk.CTkEntry(c, border_color=tema.LINHA); self.desc.pack(fill="x")
        self.estr = ctk.CTkCheckBox(c, text="Ponto estratégico (hospital, escola, creche…)", text_color=tema.TEXTO,
                                    fg_color=tema.AZUL)
        self.estr.pack(anchor="w", pady=14)
        _botao(c, "Cadastrar", self.salvar, principal=True, largura=140).pack(pady=8)

    def salvar(self):
        nome = self.nome.get().strip()
        if not nome:
            messagebox.showwarning("Faltou o nome", "Informe o nome do ponto.", parent=self)
            return
        tipo = next(k for k, v in PONTO_TIPO_LABEL.items() if v == self.tipo.get())
        rodar_em_background(
            self,
            lambda: self.api.qualidade_criar_ponto(self.localidade, tipo, nome, self.desc.get().strip(), bool(self.estr.get())),
            lambda _: (self.ao_salvar(), self.destroy()),
            lambda e: messagebox.showerror("Erro", _msg_erro(e, "Falha ao cadastrar o ponto"), parent=self),
        )


class JanelaEditarRegra(ctk.CTkToplevel):
    def __init__(self, master, api, regra, ao_salvar):
        super().__init__(master)
        self.title("Editar regra de amostragem")
        self.geometry("440x360")
        self.configure(fg_color=tema.BRANCO)
        self.api, self.regra, self.ao_salvar = api, regra, ao_salvar
        c = ctk.CTkFrame(self, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=20, pady=16)
        ctk.CTkLabel(c, text=_descricao_grupo(regra["grupo"]), wraplength=390, justify="left", anchor="w",
                     font=ctk.CTkFont(weight="bold"), text_color=tema.AZUL_ESCURO).pack(fill="x")
        ctk.CTkLabel(c, text="Quantidade por período", text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=(14, 2))
        self.qtd = ctk.CTkEntry(c, border_color=tema.LINHA); self.qtd.insert(0, str(regra["quantidade"])); self.qtd.pack(fill="x")
        ctk.CTkLabel(c, text="Período", text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=(10, 2))
        self.periodo = ctk.CTkOptionMenu(c, values=list(PERIODO_LABEL.values()), fg_color=tema.BRANCO,
                                         button_color=tema.AZUL, text_color=tema.TEXTO, dropdown_text_color=tema.TEXTO)
        self.periodo.set(PERIODO_LABEL.get(regra["periodo"], "Mensal")); self.periodo.pack(fill="x")
        self.ativo = ctk.CTkCheckBox(c, text="Regra ativa", text_color=tema.TEXTO, fg_color=tema.AZUL)
        if regra["ativo"]:
            self.ativo.select()
        self.ativo.pack(anchor="w", pady=12)
        ctk.CTkLabel(c, text="Atenção: o plano padrão segue a Portaria 888/2021. Alterar aqui marca a regra como manual "
                              "e ela deixa de ser recalculada automaticamente.", wraplength=390, justify="left",
                     text_color=tema.AMBAR, anchor="w", font=ctk.CTkFont(size=11)).pack(fill="x")
        _botao(c, "Salvar", self.salvar, principal=True, largura=140).pack(pady=12)

    def salvar(self):
        try:
            qtd = int(self.qtd.get().strip())
            if qtd < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Quantidade inválida", "Use um número inteiro (0 ou mais).", parent=self)
            return
        periodo = next(k for k, v in PERIODO_LABEL.items() if v == self.periodo.get())
        rodar_em_background(
            self,
            lambda: self.api.qualidade_editar_regra(self.regra["id"], quantidade=qtd, periodo=periodo,
                                                    ativo=bool(self.ativo.get())),
            lambda _: (self.ao_salvar(), self.destroy()),
            lambda e: messagebox.showerror("Erro", _msg_erro(e, "Falha ao salvar a regra"), parent=self),
        )


def _descricao_grupo(grupo):
    return {
        "fq_saida": "Físico-química na saída da ETA (turbidez, cloro residual, cor, pH)",
        "turbidez_filtro": "Turbidez do efluente do filtro",
        "bact_saida": "Bacteriologia na saída do tratamento",
        "bact_rede": "Bacteriologia na rede e reservatórios",
        "ecoli_captacao": "E. coli na água bruta (captação)",
        "agua_bruta_semestral": "Parâmetros da água bruta (laudo semestral)",
        "cianobacterias": "Cianobactérias no manancial",
    }.get(grupo, grupo)


class AbaPontosRegras(_AbaBase):
    def carregar(self):
        self._carregando()
        loc = self.localidade

        def buscar():
            try:
                config = self.api.qualidade_ver_config(loc)
            except ApiError:
                config = None
            return config, self.api.qualidade_listar_pontos(loc), self.api.qualidade_listar_regras(loc)

        self._pedido(buscar, self._desenhar, "Falha ao carregar pontos e regras")

    def _admin(self):
        return self.api.tipo_usuario == "admin"

    def _desenhar(self, resultado):
        config, pontos, regras = resultado
        _limpar(self)
        self._bloco_config(config)
        self._bloco_pontos(pontos)
        self._bloco_regras(regras, config)

    # -- Configuração --
    def _bloco_config(self, config):
        _titulo_secao(self, "Sistema de abastecimento desta localidade")
        caixa = ctk.CTkFrame(self, fg_color="#F6F8FB", corner_radius=8)
        caixa.pack(fill="x")
        linha = ctk.CTkFrame(caixa, fg_color="transparent")
        linha.pack(fill="x", padx=12, pady=12)
        self.e_pop = self._mini_campo(linha, "População abastecida", str(config["populacao_abastecida"]) if config else "", 150)
        self.m_man = self._mini_menu(linha, "Manancial", ["superficial", "subterraneo"], config["manancial"] if config else "superficial")
        self.m_fil = self._mini_menu(linha, "Filtração", ["lenta", "rapida"], (config or {}).get("filtracao") or "lenta")
        self.e_nf = self._mini_campo(linha, "Nº de filtros", str(config["numero_filtros"]) if config else "1", 90)
        botao = _botao(linha, "Salvar", self._salvar_config, principal=True, largura=90)
        botao.pack(side="left", padx=(12, 0), pady=(18, 0))
        if not self._admin():
            botao.configure(state="disabled")
        if not config:
            ctk.CTkLabel(caixa, text="Localidade ainda sem configuração: preencha e salve para poder gerar o plano.",
                         text_color=tema.AMBAR, anchor="w").pack(fill="x", padx=12, pady=(0, 10))

    def _mini_campo(self, master, rotulo, valor, largura):
        f = ctk.CTkFrame(master, fg_color="transparent")
        f.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(f, text=rotulo, text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=12), anchor="w").pack(fill="x")
        e = ctk.CTkEntry(f, width=largura, border_color=tema.LINHA)
        e.insert(0, valor)
        e.pack()
        return e

    def _mini_menu(self, master, rotulo, valores, atual):
        f = ctk.CTkFrame(master, fg_color="transparent")
        f.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(f, text=rotulo, text_color=tema.TEXTO_SUAVE, font=ctk.CTkFont(size=12), anchor="w").pack(fill="x")
        m = ctk.CTkOptionMenu(f, values=valores, width=130, fg_color=tema.BRANCO, button_color=tema.AZUL,
                              text_color=tema.TEXTO, dropdown_text_color=tema.TEXTO)
        m.set(atual)
        m.pack()
        return m

    def _salvar_config(self):
        try:
            pop = int(self.e_pop.get().strip())
            nf = int(self.e_nf.get().strip())
            if pop <= 0 or nf <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Valor inválido", "População e nº de filtros devem ser números inteiros maiores que zero.")
            return
        loc, man, fil = self.localidade, self.m_man.get(), self.m_fil.get()
        rodar_em_background(
            self, lambda: self.api.qualidade_salvar_config(loc, pop, man, fil, nf),
            lambda _: (messagebox.showinfo("Salvo", "Configuração salva. Se mudou população ou filtros, gere o plano de novo."),
                       self.carregar()),
            lambda e: messagebox.showerror("Erro", _msg_erro(e, "Falha ao salvar a configuração")),
        )

    # -- Pontos --
    def _bloco_pontos(self, pontos):
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", pady=(18, 6))
        ctk.CTkLabel(cab, text="Pontos de coleta", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=tema.AZUL_ESCURO).pack(side="left")
        if self._admin() or self.api.tipo_usuario == "quimico":
            _botao(cab, "+ Novo ponto", lambda: JanelaNovoPonto(self, self.api, self.localidade, self.carregar),
                   principal=True, largura=110).pack(side="right")
        if not pontos:
            ctk.CTkLabel(self, text="Nenhum ponto cadastrado.", text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x")
        for p in pontos:
            linha = ctk.CTkFrame(self, fg_color="#F6F8FB" if p["ativo"] else "#EEEEEE", corner_radius=8)
            linha.pack(fill="x", pady=2)
            linha.grid_columnconfigure(0, weight=1)
            nome = f"{p['nome']}" + ("  ★ estratégico" if p["estrategico"] else "") + ("" if p["ativo"] else "  (inativo)")
            ctk.CTkLabel(linha, text=nome, anchor="w", text_color=tema.TEXTO if p["ativo"] else tema.TEXTO_SUAVE,
                         font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", padx=12, pady=(7, 0))
            ctk.CTkLabel(linha, text=PONTO_TIPO_LABEL.get(p["tipo"], p["tipo"]) + (f" · {p['descricao']}" if p.get("descricao") else ""),
                         anchor="w", text_color=tema.TEXTO_SUAVE).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 7))
            if self._admin() or self.api.tipo_usuario == "quimico":
                _botao(linha, "Desativar" if p["ativo"] else "Reativar", lambda p=p: self._alternar_ponto(p),
                       largura=90).grid(row=0, column=1, rowspan=2, padx=12)

    def _alternar_ponto(self, ponto):
        rodar_em_background(
            self, lambda: self.api.qualidade_editar_ponto(ponto["id"], ativo=not ponto["ativo"]),
            lambda _: self.carregar(),
            lambda e: messagebox.showerror("Erro", _msg_erro(e, "Falha ao atualizar o ponto")),
        )

    # -- Regras --
    def _bloco_regras(self, regras, config):
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", pady=(18, 6))
        ctk.CTkLabel(cab, text="Plano de amostragem (regras)", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=tema.AZUL_ESCURO).pack(side="left")
        botao = _botao(cab, "Gerar plano mínimo da norma", self._gerar_plano, principal=True, largura=200)
        botao.pack(side="right")
        if not self._admin() or not config:
            botao.configure(state="disabled")
        if not regras:
            ctk.CTkLabel(self, text="Nenhuma regra ainda. Salve a configuração acima e gere o plano.",
                         text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x")
        for r in regras:
            linha = ctk.CTkFrame(self, fg_color="#F6F8FB" if r["ativo"] else "#EEEEEE", corner_radius=8)
            linha.pack(fill="x", pady=2)
            linha.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(linha, text=_descricao_grupo(r["grupo"]), anchor="w", wraplength=520, justify="left",
                         text_color=tema.TEXTO, font=ctk.CTkFont(weight="bold")
                         ).grid(row=0, column=0, sticky="w", padx=12, pady=(7, 0))
            det = f"{PONTO_TIPO_LABEL.get(r['ponto_tipo'], r['ponto_tipo'])} · {r['quantidade']}× {PERIODO_LABEL.get(r['periodo'], r['periodo']).lower()}"
            if r.get("norma"):
                det += f" · {r['norma']}"
            if r["manual"]:
                det += " · ajustada manualmente"
            if not r["ativo"]:
                det += " · INATIVA"
            ctk.CTkLabel(linha, text=det, anchor="w", text_color=tema.TEXTO_SUAVE, wraplength=520, justify="left"
                         ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 7))
            b = _botao(linha, "Editar", lambda r=r: JanelaEditarRegra(self, self.api, r, self.carregar), largura=80)
            b.grid(row=0, column=1, rowspan=2, padx=12)
            if not self._admin():
                b.configure(state="disabled")

    def _gerar_plano(self):
        if not messagebox.askyesno(
            "Gerar plano mínimo da norma",
            "Isto recalcula as regras automáticas com base na população e na configuração acima.\n"
            "Regras que você ajustou manualmente são preservadas.\n\nContinuar?",
        ):
            return
        loc = self.localidade

        def sucesso(res):
            avisos = "\n".join(f"• {a}" for a in res.get("avisos", []))
            messagebox.showinfo("Plano gerado", f"{len(res.get('regras', []))} regra(s) no plano." + (f"\n\nAvisos:\n{avisos}" if avisos else ""))
            self.carregar()

        rodar_em_background(self, lambda: self.api.qualidade_gerar_regras(loc), sucesso,
                            lambda e: messagebox.showerror("Erro", _msg_erro(e, "Falha ao gerar o plano")))


# ----------------------------------------------------------------------------
# Tela principal
# ----------------------------------------------------------------------------
class AreaQuimico(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color=tema.FUNDO)
        self.api = api
        self._localidades = list(LOCALIDADE_LABEL.keys())
        self._meses = _meses_disponiveis()
        self._atual = None

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=24, pady=(20, 6))
        titulos = ctk.CTkFrame(topo, fg_color="transparent")
        titulos.pack(side="left")
        ctk.CTkLabel(titulos, text="Área do Químico", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x")
        ctk.CTkLabel(titulos, text="Qualidade da água · Portaria GM/MS 888/2021", font=ctk.CTkFont(size=12),
                     text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x")
        _botao(topo, "Relatório mensal (PDF)", self.baixar_pdf, principal=True, largura=170).pack(side="right")
        _botao(topo, "Atualizar", self.recarregar, largura=90).pack(side="right", padx=8)
        self.menu_mes = ctk.CTkOptionMenu(
            topo, values=[r for r, _ in self._meses], width=150, command=lambda _: self.recarregar(),
            fg_color=tema.BRANCO, button_color=tema.AZUL, button_hover_color=tema.AZUL_HOVER,
            text_color=tema.TEXTO, dropdown_text_color=tema.TEXTO)
        self.menu_mes.pack(side="right", padx=(0, 8))
        self.menu_loc = ctk.CTkOptionMenu(
            topo, values=[LOCALIDADE_LABEL[l] for l in self._localidades], width=150,
            command=lambda _: self.recarregar(), fg_color=tema.BRANCO, button_color=tema.AZUL,
            button_hover_color=tema.AZUL_HOVER, text_color=tema.TEXTO, dropdown_text_color=tema.TEXTO)
        self.menu_loc.pack(side="right", padx=(0, 8))

        # Barra de abas própria (sublinhado azul na aba ativa), como no esboço aprovado.
        self.faixa_alertas = FaixaAlertas(self)  # aparece só quando há alerta (empacotada pelo acompanhamento ao vivo)
        barra_abas = self._barra_abas = ctk.CTkFrame(self, fg_color="transparent", height=36)
        barra_abas.pack(fill="x", padx=24, pady=(6, 0))
        ctk.CTkFrame(self, height=1, fg_color=tema.LINHA).pack(fill="x", padx=24)
        self.area = ctk.CTkFrame(self, fg_color="transparent")
        self.area.pack(fill="both", expand=True, padx=24, pady=(8, 16))
        self.conteudo, self._botoes_aba, self._sublinhas = {}, {}, {}
        for nome, classe in (("Ao vivo", AbaAoVivo), ("Conformidade", AbaConformidade), ("Análises da ETA", AbaAnalisesEta),
                             ("Coletas e resultados", AbaColetas), ("Laudos", AbaLaudos),
                             ("Pontos e regras", AbaPontosRegras)):
            coluna = ctk.CTkFrame(barra_abas, fg_color="transparent")
            coluna.pack(side="left", padx=(0, 6))
            b = ctk.CTkButton(coluna, text=nome, width=10, fg_color="transparent", hover_color=tema.AZUL_CLARO,
                              text_color=tema.TEXTO_SUAVE, corner_radius=4, command=lambda n=nome: self._selecionar(n))
            b.pack()
            linha = ctk.CTkFrame(coluna, height=2, fg_color="transparent")
            linha.pack(fill="x")
            self._botoes_aba[nome], self._sublinhas[nome] = b, linha
            self.conteudo[nome] = classe(self.area, api)
        self._atual = None
        self._carregadas = set()
        self._selecionar("Ao vivo")
        self._iniciar_ao_vivo()

    # --- acompanhamento ao vivo: consulta o servidor a cada 15 s, em qualquer aba -------------------------
    def _iniciar_ao_vivo(self):
        self._ids_vivo = [0, 0]
        self._alertas_vistos = None  # None = primeira consulta (não toca o aviso sonoro)
        self._vivo_ativo = True
        self._timer_vivo = None
        self._consultar_ao_vivo()

    def _consultar_ao_vivo(self):
        if not self._vivo_ativo or not self.winfo_exists():
            return
        ids = list(self._ids_vivo)
        rodar_em_background(self, lambda: self.api.analises_ao_vivo(*ids), self._chegou_ao_vivo, self._falhou_ao_vivo)

    def _agendar_ao_vivo(self):
        if self._vivo_ativo and self.winfo_exists():
            self._timer_vivo = self.after(INTERVALO_MS, self._consultar_ao_vivo)

    def _chegou_ao_vivo(self, dados):
        if not self._vivo_ativo or not self.winfo_exists():
            return
        self._ids_vivo = [dados["ultimo_id_analise"], dados["ultimo_id_lavagem"]]
        novas, _fora = self.conteudo["Ao vivo"].receber(dados)
        alertas = alertas_de(dados["localidades"])
        chaves = {a[0] for a in alertas}
        if self._alertas_vistos is not None and chaves - self._alertas_vistos:
            try:
                self.bell()  # aviso sonoro só quando surge um problema novo
            except Exception:
                pass
        self._alertas_vistos = chaves
        self.faixa_alertas.mostrar(alertas)
        if alertas and not self.faixa_alertas.winfo_ismapped():
            self.faixa_alertas.pack(fill="x", padx=24, pady=(0, 6), before=self._barra_abas)
        if novas:  # a aba "Análises da ETA" precisa recarregar na próxima vez que abrir (ou agora, se estiver aberta)
            self._carregadas.discard("Análises da ETA")
            if self._atual == "Análises da ETA":
                self._ao_trocar_aba()
        self._agendar_ao_vivo()

    def _falhou_ao_vivo(self, erro):
        if not self._vivo_ativo or not self.winfo_exists():
            return
        self.conteudo["Ao vivo"].falhou(_msg_erro(erro, "falha de conexão"))
        self._agendar_ao_vivo()

    def destroy(self):
        self._vivo_ativo = False
        if getattr(self, "_timer_vivo", None):
            try:
                self.after_cancel(self._timer_vivo)
            except Exception:
                pass
        super().destroy()

    def _selecionar(self, nome):
        for n, b in self._botoes_aba.items():
            ativo = n == nome
            b.configure(text_color=tema.AZUL if ativo else tema.TEXTO_SUAVE,
                        font=ctk.CTkFont(weight="bold" if ativo else "normal"))
            self._sublinhas[n].configure(fg_color=tema.AZUL if ativo else "transparent")
            if ativo:
                self.conteudo[n].pack(fill="both", expand=True)
            else:
                self.conteudo[n].pack_forget()
        self._atual = nome
        self._ao_trocar_aba()

    def _localidade(self):
        rot = self.menu_loc.get()
        return next(k for k, v in LOCALIDADE_LABEL.items() if v == rot)

    def _mes(self):
        rot = self.menu_mes.get()
        return next(v for r, v in self._meses if r == rot)

    def recarregar(self):
        """Contexto mudou (localidade/mês): só a aba visível carrega; as outras carregam ao serem abertas."""
        self._carregadas = set()
        self._ao_trocar_aba()

    def _ao_trocar_aba(self):
        nome = self._atual
        if nome in self._carregadas:
            return
        self._carregadas.add(nome)
        self.conteudo[nome].definir_contexto(self._localidade(), self._mes())

    def baixar_pdf(self):
        loc, mes = self._localidade(), self._mes()

        def sucesso(conteudo):
            caminho = filedialog.asksaveasfilename(
                defaultextension=".pdf", initialfile=f"relatorio-qualidade-{loc}-{mes}.pdf",
                filetypes=[("PDF", "*.pdf")])
            if not caminho:
                return
            with open(caminho, "wb") as f:
                f.write(conteudo)
            try:
                os.startfile(caminho)
            except Exception:
                messagebox.showinfo("Salvo", f"Relatório salvo em: {caminho}")

        rodar_em_background(self, lambda: self.api.qualidade_relatorio_pdf(loc, mes), sucesso,
                            lambda e: messagebox.showerror("Erro", _msg_erro(e, "Falha ao gerar o relatório")))
