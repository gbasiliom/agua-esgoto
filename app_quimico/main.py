import json
import os
from datetime import datetime

from kivy.utils import platform
from kivy.core.window import Window
if platform not in ("android", "ios"):
    Window.size = (400, 760)

from kivy.uix.screenmanager import Screen
from kivy.clock import Clock
from kivy.properties import StringProperty
from kivymd.app import MDApp
from kivymd.uix.list import TwoLineListItem, OneLineListItem

from base_app import AppSiga, TelaLoginBase, numero, agora_iso
from api_client import ApiClient, ApiError, ErroConexao
from async_helper import rodar_em_background
import ao_vivo_util as vivo

LOCALIDADES = [("sede", "Chalé (sede)"), ("penha_do_coco", "Penha do Coco"), ("bananal", "Bananal"), ("agua_limpa", "Água Limpa")]
PONTO_TIPO_LABEL = {"captacao": "Captação", "saida_eta": "Saída da ETA", "reservatorio": "Reservatório", "rede": "Rede"}
GRUPO_LABEL = {
    "fq_saida": "Físico-química (saída ETA)", "turbidez_filtro": "Turbidez do filtro", "bact_saida": "Bacteriologia (saída)",
    "bact_rede": "Bacteriologia (rede)", "ecoli_captacao": "E. coli (captação)",
    "agua_bruta_semestral": "Água bruta semestral (laudo externo)", "cianobacterias": "Cianobactérias",
}
# Grupos coletáveis em cada tipo de ponto (espelha qualidade_regras.GRUPO_PONTO_TIPO)
GRUPOS_POR_PONTO = {
    "saida_eta": ["bact_saida"], "rede": ["bact_rede"], "reservatorio": ["bact_rede"],
    "captacao": ["ecoli_captacao", "cianobacterias", "agua_bruta_semestral"],
}
GRUPOS_BACT = ("bact_saida", "bact_rede")
STATUS_REDE = {"ok": "OK", "atencao": "ATENÇÃO", "violacao": "VIOLAÇÃO DO PADRÃO"}
STATUS_REGRA = {"ok": "OK", "deficit": "DÉFICIT", "em_andamento": "em andamento"}
STATUS_AMOSTRA = {"pendente": "PENDENTE de coleta", "coletada": "Coletada", "analisada": "Analisada",
                  "encaminhada": "Encaminhada ao laboratório", "laudo_recebido": "Laudo recebido"}
TIPOS_LAUDO = [("agua_bruta_semestral", "Água bruta semestral"), ("bacteriologico", "Bacteriológico"), ("outro", "Outro")]


def _app():
    return MDApp.get_running_app()


def _erro_em(widget):
    return lambda e: setattr(widget, "text", str(e))


class TelaLogin(TelaLoginBase):
    tipos_aceitos = ("quimico",)

    def ao_logar(self):
        _app().iniciar_ao_vivo()
        self.manager.current = "home"


class TelaHome(Screen):
    def on_pre_enter(self):
        app = _app()
        self.ids.cab.titulo = app.api.nome or ""
        self.carregar()

    def escolher(self, chave):
        _app().localidade = chave
        self.carregar()

    def carregar(self):
        app = _app()
        loc = app.localidade
        nome = dict(LOCALIDADES)[loc]
        self.ids.cab.subtitulo = f"Químico · {nome}"
        self.ids.lista.clear_widgets()
        self.ids.resumo.text = "Carregando..."
        self.ids.alertas.text = ""

        def ok(d):
            if loc == app.localidade:  # descarta resposta de uma localidade que já foi trocada
                self._mostrar(d)

        def erro(e):
            self.ids.resumo.text = str(e)

        rodar_em_background(lambda: app.api.conformidade(loc), ok, erro)

    def _mostrar(self, d):
        app = _app()
        lista = self.ids.lista
        lista.clear_widgets()
        pop = d.get("populacao_abastecida")
        self.ids.resumo.text = (f"{d['mes']} · população abastecida {pop} · manancial {d.get('manancial') or '—'}"
                                if pop else "Sistema ainda não configurado. Peça ao administrador (painel Windows).")
        alertas = list(d.get("alertas", []))
        self.ids.alertas.text = "\n".join(f"• {a}" for a in alertas)
        for r in d["regras"]:
            lista.add_widget(TwoLineListItem(
                text=f"{GRUPO_LABEL.get(r['grupo'], r['grupo'])}: {r['realizado']}/{r['exigido']} · {STATUS_REGRA.get(r['status'], r['status'])}",
                secondary_text=f"{r.get('norma') or ''} · {r['quantidade_por_periodo']} por {r['periodo']}"))
        rede = d["rede"]
        if rede["status"] != "sem_dados":
            lista.add_widget(TwoLineListItem(
                text=f"Padrão da rede no mês: {STATUS_REDE.get(rede['status'], rede['status'])}",
                secondary_text=f"{rede['amostras_analisadas']} amostras · {rede['com_coliformes_totais']} com coliformes · {rede['com_e_coli']} com E. coli"))
        for rc in d["recoletas_pendentes"]:
            lista.add_widget(TwoLineListItem(
                text=f"RECOLETA {'ATRASADA ' if rc['atrasada'] else ''}{rc['codigo']} ({rc['posicao']})",
                secondary_text=f"prevista para {rc['data_prevista']}"))

    def trocar_senha(self):
        self.manager.get_screen("trocar_senha").abrir(obrigatoria=False, voltar_para="home")
        self.manager.current = "trocar_senha"

    def sair(self):
        app = _app()
        app.parar_ao_vivo()
        app.encerrar_sessao()
        app.api = None
        self.manager.current = "login"


class TelaAoVivo(Screen):
    """Situação de cada ETA + últimos lançamentos dos operadores. Atualiza sozinha enquanto estiver aberta."""

    def on_pre_enter(self):
        self.redesenhar()

    def redesenhar(self):
        app = _app()
        est = app.vivo
        self.ids.status.text = app.vivo_status
        self.ids.status.text_color = app.c_vermelho if app.vivo_erro else app.c_ok
        lista = self.ids.lista
        lista.clear_widgets()
        for l in est.localidades:
            rotulo, nivel = vivo.situacao_texto(l)
            nome = vivo.LOCALIDADE_LABEL.get(l["localidade"], l["localidade"])
            if l["tem_dados"]:
                sec = f"Última análise às {vivo.hora_br(l['ultima_coleta'])} (há {vivo.duracao_texto(l['minutos_desde_ultima'])})"
                if l["atrasada"]:
                    sec += f" · atrasada em {vivo.duracao_texto(l['minutos_atraso'])}"
            else:
                sec = "Nenhuma análise registrada"
            item = TwoLineListItem(text=f"{nome} — {rotulo}", secondary_text=sec)
            if nivel in ("erro", "atraso"):
                item.theme_text_color = "Custom"
                item.text_color = app.c_vermelho if nivel == "erro" else app.c_ambar
            lista.add_widget(item)
        if est.eventos:
            lista.add_widget(OneLineListItem(text="— Últimos lançamentos —"))
        for e in est.eventos:
            texto, sec = vivo.linha_analise(e["dados"]) if e["tipo"] == "analise" else vivo.linha_lavagem(e["dados"])
            item = TwoLineListItem(text=texto, secondary_text=sec)
            if e["tipo"] == "analise" and e["dados"].get("conforme") is False:
                item.theme_text_color = "Custom"
                item.text_color = app.c_vermelho
            lista.add_widget(item)
        if not est.localidades:
            self.ids.status.text = app.vivo_status or "Conectando…"


class TelaAmostras(Screen):
    def on_pre_enter(self):
        app = _app()
        self.ids.lista.clear_widgets()
        self.ids.msg.text = "Carregando..."

        def ok(amostras):
            self.ids.lista.clear_widgets()
            self.ids.msg.text = "" if amostras else "Nenhuma amostra ainda."
            amostras.sort(key=lambda a: (a["status"] != "pendente", -a["id"]))
            for a in amostras:
                item = TwoLineListItem(
                    text=f"{a['codigo'] or a['id']} · {GRUPO_LABEL.get(a['grupo'], a['grupo'])}",
                    secondary_text=f"{STATUS_AMOSTRA.get(a['status'], a['status'])}" + (" · recoleta" if a.get("recoleta_de_id") else ""))
                item.bind(on_release=lambda w, a=a: self.abrir(a))
                self.ids.lista.add_widget(item)

        rodar_em_background(lambda: app.api.amostras(app.localidade), ok, _erro_em(self.ids.msg))

    def abrir(self, amostra):
        tela = self.manager.get_screen("detalhe")
        tela.amostra = amostra
        self.manager.current = "detalhe"


class TelaNovaColeta(Screen):
    ponto = None

    def on_pre_enter(self):
        app = _app()
        self.ponto = None
        self.ids.msg.text = ""
        self.ids.escolhido.text = "Toque no ponto de coleta"
        self._limpar_grupos()
        for c in ("cloro", "cor", "turbidez", "obs"):
            self.ids[c].text = ""
        self.ids.lista.clear_widgets()
        self._mostrar_cadastrar(False)

        def ok(pontos):
            self.ids.lista.clear_widgets()
            self.pontos = pontos
            self._mostrar_cadastrar(not pontos)
            if not pontos:
                self.ids.escolhido.text = "Nenhum ponto de coleta cadastrado nesta localidade."
                self.ids.msg.text = "Cadastre ao menos um ponto (ex.: um ponto da rede) para registrar a coleta."
            for p in pontos:
                it = OneLineListItem(text=f"{PONTO_TIPO_LABEL.get(p['tipo'], p['tipo'])} · {p['nome']}")
                it.bind(on_release=lambda w, p=p: self.escolher(p))
                self.ids.lista.add_widget(it)

        rodar_em_background(lambda: app.api.pontos(app.localidade), ok, _erro_em(self.ids.msg))

    def _mostrar_cadastrar(self, visivel):
        """Botão que leva ao cadastro de pontos quando a localidade ainda não tem nenhum."""
        from kivy.metrics import dp
        b = self.ids.bt_cadastrar
        b.height = dp(48) if visivel else 0
        b.opacity = 1 if visivel else 0
        b.disabled = not visivel

    def _limpar_grupos(self):
        self.grupo = None
        self.ids.grupos.clear_widgets()

    def escolher(self, ponto):
        from kivymd.uix.button import MDFlatButton
        self.ponto = ponto
        self.ids.escolhido.text = f"{PONTO_TIPO_LABEL.get(ponto['tipo'])} · {ponto['nome']}"
        self._limpar_grupos()
        for g in GRUPOS_POR_PONTO.get(ponto["tipo"], []):
            b = MDFlatButton(text=GRUPO_LABEL[g], size_hint_x=1)
            b.bind(on_release=lambda w, g=g: self.escolher_grupo(g))
            self.ids.grupos.add_widget(b)
        if len(GRUPOS_POR_PONTO.get(ponto["tipo"], [])) == 1:
            self.escolher_grupo(GRUPOS_POR_PONTO[ponto["tipo"]][0])

    def escolher_grupo(self, g):
        self.grupo = g
        self.ids.grupo_escolhido.text = f"Finalidade: {GRUPO_LABEL[g]}"

    def registrar(self):
        app = _app()
        if not self.ponto or not self.grupo:
            self.ids.msg.text = ("Escolha o ponto e a finalidade." if getattr(self, "pontos", None)
                                 else "Cadastre um ponto de coleta antes de registrar a coleta.")
            return
        try:
            dados = {"ponto_id": self.ponto["id"], "grupo": self.grupo, "coletado_em": agora_iso(),
                     "cloro_residual": numero(self.ids.cloro.text), "cor_aparente": numero(self.ids.cor.text),
                     "turbidez": numero(self.ids.turbidez.text), "observacoes": self.ids.obs.text.strip() or None}
        except ValueError:
            self.ids.msg.text = "Valor numérico inválido."
            return
        if self.grupo in GRUPOS_BACT and None in (dados["cloro_residual"], dados["cor_aparente"], dados["turbidez"]):
            self.ids.msg.text = "Em amostra bacteriológica meça cloro residual, cor e turbidez no ato da coleta (Art. 44 §3)."
            return
        self.ids.msg.text = "Enviando..."

        def ok(a):
            app.aviso(f"Amostra {a['codigo']} registrada.\nColoque a etiqueta/código no frasco.", "Coleta registrada")
            self.manager.get_screen("detalhe").amostra = a
            self.manager.current = "detalhe"

        rodar_em_background(lambda: app.api.criar_amostra(dados), ok, _erro_em(self.ids.msg))


class TelaDetalhe(Screen):
    amostra = None
    ct = None   # None = não informado, True/False
    ec = None

    def on_pre_enter(self):
        a = self.amostra
        self.ct = self.ec = None
        g = a["grupo"]
        self.ids.titulo.text = f"{a['codigo'] or a['id']} · {GRUPO_LABEL.get(g, g)}"
        self.ids.status.text = STATUS_AMOSTRA.get(a["status"], a["status"])
        self.ids.msg.text = ""
        for c in ("cloro", "cor", "turbidez", "nmp", "cel", "metodo", "lote"):
            self.ids[c].text = ""
        pend = a["status"] == "pendente"
        coletada = a["status"] in ("coletada", "encaminhada") and not pend
        bact = g in GRUPOS_BACT
        self._mostrar("bloco_coleta", pend)
        self._mostrar("bloco_bact", coletada and bact)
        self._mostrar("bloco_nmp", coletada and g == "ecoli_captacao")
        self._mostrar("bloco_cel", coletada and g == "cianobacterias")
        self._mostrar("bloco_encaminhar", coletada and g == "agua_bruta_semestral" and a["status"] == "coletada")
        self._rotulos()
        self.ids.info.text = self._info_texto(a)

    def _info_texto(self, a):
        partes = []
        if a.get("coletado_em"):
            partes.append(f"Coletada em {a['coletado_em'][:16].replace('T', ' ')}")
        if a.get("data_prevista") and a["status"] == "pendente":
            partes.append(f"Prevista para {a['data_prevista']}")
        for k, r in (("cloro_residual", "cloro"), ("cor_aparente", "cor"), ("turbidez", "turbidez")):
            if a.get(k) is not None:
                partes.append(f"{r}: {a[k]:g}")
        if a.get("posicao_recoleta"):
            partes.append(f"Recoleta ({a['posicao_recoleta']})")
        if a["status"] == "analisada":
            partes.append("Resultado já lançado.")
        return " · ".join(partes)

    def _mostrar(self, nome, visivel):
        w = self.ids[nome]
        w.opacity = 1 if visivel else 0
        w.disabled = not visivel
        if not hasattr(w, "_altura_cheia"):
            w._altura_cheia = w.height
        w.height = w._altura_cheia if visivel else 0

    def _rotulos(self):
        r = {None: "TOQUE PARA ESCOLHER", True: "PRESENTE", False: "AUSENTE"}
        self.ids.bt_ct.text = f"Coliformes totais: {r[self.ct]}"
        self.ids.bt_ec.text = f"E. coli: {r[self.ec]}"

    def alternar(self, qual):
        atual = getattr(self, qual)
        setattr(self, qual, {None: False, False: True, True: False}[atual])
        self._rotulos()

    def salvar_coleta(self):
        app = _app()
        try:
            dados = {"coletado_em": agora_iso(), "cloro_residual": numero(self.ids.cloro.text),
                     "cor_aparente": numero(self.ids.cor.text), "turbidez": numero(self.ids.turbidez.text)}
        except ValueError:
            self.ids.msg.text = "Valor numérico inválido."
            return
        if self.amostra["grupo"] in GRUPOS_BACT and None in (dados["cloro_residual"], dados["cor_aparente"], dados["turbidez"]):
            self.ids.msg.text = "Informe cloro residual, cor e turbidez (Art. 44 §3)."
            return

        def ok(a):
            self.amostra = a
            self.on_pre_enter()
            app.aviso("Coleta registrada. Agora lance o resultado quando sair a leitura.")

        rodar_em_background(lambda: app.api.registrar_coleta(self.amostra["id"], dados), ok, _erro_em(self.ids.msg))

    def salvar_resultado(self):
        app = _app()
        g = self.amostra["grupo"]
        try:
            if g in GRUPOS_BACT:
                if self.ct is None or self.ec is None:
                    self.ids.msg.text = "Escolha Presente/Ausente para coliformes totais E E. coli."
                    return
                dados = {"coliformes_totais_presente": self.ct, "e_coli_presente": self.ec,
                         "metodo": self.ids.metodo.text.strip() or None, "lote_kit": self.ids.lote.text.strip() or None}
            elif g == "ecoli_captacao":
                v = numero(self.ids.nmp.text)
                if v is None:
                    self.ids.msg.text = "Informe o resultado em NMP/100 mL."
                    return
                dados = {"e_coli_nmp": v}
            else:
                v = numero(self.ids.cel.text)
                if v is None:
                    self.ids.msg.text = "Informe a contagem em células/mL."
                    return
                dados = {"cianobacterias_cel_ml": v}
        except ValueError:
            self.ids.msg.text = "Valor numérico inválido."
            return

        def ok(r):
            txt = "Resultado registrado."
            if r["alertas"]:
                txt += "\n\nATENÇÃO:\n- " + "\n- ".join(r["alertas"])
            if r["recoletas_criadas"]:
                txt += f"\n\n{len(r['recoletas_criadas'])} recoleta(s) criada(s) para amanhã — veja em Amostras."
            app.aviso(txt, "Resultado")
            self.manager.current = "amostras"

        rodar_em_background(lambda: app.api.lancar_resultado(self.amostra["id"], dados), ok, _erro_em(self.ids.msg))

    def encaminhar(self):
        app = _app()

        def ok(a):
            app.aviso("Amostra marcada como encaminhada ao laboratório. Quando chegar o laudo, anexe em 'Laudos'.")
            self.manager.current = "amostras"

        rodar_em_background(lambda: app.api.encaminhar(self.amostra["id"]), ok, _erro_em(self.ids.msg))


class TelaPontos(Screen):
    tipo = "rede"

    def on_pre_enter(self):
        self.ids.msg.text = ""
        self.ids.nome.text = ""
        self.tipo = "rede"
        self.ids.bt_tipo.text = f"Tipo: {PONTO_TIPO_LABEL[self.tipo]} (toque para trocar)"
        self.listar()

    def trocar_tipo(self):
        ordem = list(PONTO_TIPO_LABEL)
        self.tipo = ordem[(ordem.index(self.tipo) + 1) % len(ordem)]
        self.ids.bt_tipo.text = f"Tipo: {PONTO_TIPO_LABEL[self.tipo]} (toque para trocar)"

    def listar(self):
        app = _app()
        self.ids.lista.clear_widgets()

        def ok(pontos):
            self.ids.lista.clear_widgets()
            for p in pontos:
                self.ids.lista.add_widget(OneLineListItem(text=f"{PONTO_TIPO_LABEL.get(p['tipo'])} · {p['nome']}"))

        rodar_em_background(lambda: app.api.pontos(app.localidade), ok, _erro_em(self.ids.msg))

    def salvar(self):
        app = _app()
        nome = self.ids.nome.text.strip()
        if not nome:
            self.ids.msg.text = "Dê um nome ao ponto (ex.: 'Escola', 'Reservatório Alto')."
            return

        def ok(_):
            self.ids.nome.text = ""
            self.ids.msg.text = "Ponto cadastrado."
            self.listar()

        rodar_em_background(lambda: app.api.criar_ponto(app.localidade, self.tipo, nome), ok, _erro_em(self.ids.msg))


class TelaLaudos(Screen):
    arquivo = None
    tipo = "agua_bruta_semestral"

    def on_pre_enter(self):
        app = _app()
        self.arquivo = None
        self.tipo = "agua_bruta_semestral"
        self.ids.bt_tipo.text = "Tipo: Água bruta semestral (toque para trocar)"
        self.ids.arquivo.text = "Nenhum arquivo anexado"
        for c in ("lab", "numero", "data_coleta", "obs"):
            self.ids[c].text = ""
        self.ids.data_coleta.text = datetime.now().strftime("%d/%m/%Y")
        self.ids.msg.text = ""
        self.ids.lista.clear_widgets()

        def ok(laudos):
            self.ids.lista.clear_widgets()
            for l in laudos:
                self.ids.lista.add_widget(TwoLineListItem(
                    text=f"{l['data_coleta']} · {l['laboratorio']} · {l['tipo']}",
                    secondary_text=f"Laudo {l.get('numero_laudo') or '—'}" + (" · com arquivo" if l["tem_arquivo"] else " · SEM arquivo")))

        rodar_em_background(lambda: app.api.laudos(app.localidade), ok, _erro_em(self.ids.msg))

    def trocar_tipo(self):
        ordem = [t for t, _ in TIPOS_LAUDO]
        self.tipo = ordem[(ordem.index(self.tipo) + 1) % len(ordem)]
        self.ids.bt_tipo.text = f"Tipo: {dict(TIPOS_LAUDO)[self.tipo]} (toque para trocar)"

    def escolher_arquivo(self):
        try:
            from plyer import filechooser
            filechooser.open_file(on_selection=self._selecionado, filters=[["Laudo", "*.pdf", "*.jpg", "*.jpeg", "*.png"]])
        except Exception:
            self.ids.msg.text = "Não foi possível abrir o seletor de arquivos neste aparelho."

    def _selecionado(self, selecao):
        if selecao:
            self.arquivo = selecao[0]
            self.ids.arquivo.text = os.path.basename(self.arquivo)

    def enviar(self):
        app = _app()
        try:
            data = datetime.strptime(self.ids.data_coleta.text.strip(), "%d/%m/%Y").date().isoformat()
        except ValueError:
            self.ids.msg.text = "Data de coleta no formato dd/mm/aaaa."
            return
        lab = self.ids.lab.text.strip()
        if not lab:
            self.ids.msg.text = "Informe o laboratório."
            return
        campos = {"localidade": app.localidade, "tipo": self.tipo, "laboratorio": lab, "data_coleta": data,
                  "numero_laudo": self.ids.numero.text.strip(), "observacoes": self.ids.obs.text.strip()}

        def ok(_):
            app.aviso("Laudo registrado." + ("" if self.arquivo else "\nAtenção: sem arquivo anexado. Anexe o PDF/foto do laudo quando puder."))
            self.on_pre_enter()

        rodar_em_background(lambda: app.api.enviar_laudo(campos, self.arquivo), ok, _erro_em(self.ids.msg))


class QuimicoApp(AppSiga):
    title = "SIGA · Químico"
    api = None
    localidade = "sede"
    alertas_vivo_texto = StringProperty("")   # faixa vermelha na tela inicial
    vivo_status = ""
    vivo_erro = False
    _relogio_vivo = None

    # --- acompanhamento ao vivo: consulta o servidor a cada 15 s enquanto o químico estiver logado -------------
    def iniciar_ao_vivo(self):
        self.parar_ao_vivo()
        self.vivo = vivo.EstadoAoVivo()
        self.vivo_status, self.vivo_erro = "Conectando…", False
        self._relogio_vivo = Clock.schedule_interval(lambda dt: self._consultar_vivo(), vivo.INTERVALO_S)
        self._consultar_vivo()

    def parar_ao_vivo(self):
        if self._relogio_vivo:
            self._relogio_vivo.cancel()
            self._relogio_vivo = None
        self.alertas_vivo_texto = ""

    def _consultar_vivo(self):
        api = self.api
        if api is None or self._relogio_vivo is None:
            return
        ids = list(self.vivo.ids)

        def ok(dados):
            if self.api is not api:  # saiu/trocou de usuário enquanto a resposta vinha
                return
            novos = self.vivo.receber(dados)
            self.vivo_erro = False
            self.vivo_status = f"Ao vivo — atualiza a cada {vivo.INTERVALO_S} s · última verificação {datetime.now():%H:%M:%S}"
            self.alertas_vivo_texto = "\n".join("• " + t for _c, t in self.vivo.alertas)
            if novos:
                self.aviso("\n\n".join(novos), "Atenção — ETA")
            self._atualizar_tela_vivo()

        def erro(e):
            if self.api is not api:
                return
            self.vivo_erro = True
            self.vivo_status = f"Sem conexão — tentando de novo em {vivo.INTERVALO_S} s"
            self._atualizar_tela_vivo()

        rodar_em_background(lambda: api.analises_ao_vivo(*ids), ok, erro)

    def _atualizar_tela_vivo(self):
        if self.root and self.root.current == "ao_vivo":
            self.root.get_screen("ao_vivo").redesenhar()

    def criar_api(self):
        return ApiClient(self.url_api)

    def build(self):
        self.nome_app = "SIGA · Químico"
        with open(os.path.join(self.pasta_app, "telas_quimico.kv"), encoding="utf-8") as f:
            return self.carregar_base(f.read())


if __name__ == "__main__":
    QuimicoApp().run()
