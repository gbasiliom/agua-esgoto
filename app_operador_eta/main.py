import json
import os
from datetime import datetime, timedelta

from kivy.clock import Clock
from kivy.utils import platform
from kivy.core.window import Window
if platform not in ("android", "ios"):
    Window.size = (400, 760)

from kivy.uix.screenmanager import Screen
from kivymd.app import MDApp
from kivymd.uix.list import TwoLineListItem

from base_app import AppSiga, TelaLoginBase, numero, agora_iso
from api_client import ApiClient, ApiError, ErroConexao, ErroSessao
from async_helper import rodar_em_background
import fila_local
import regras_locais

INTERVALO_H = 2  # frequência pedida pelo SAAE: uma análise a cada 2 horas
LOCALIDADE_LABEL = {"sede": "Chalé (sede)", "penha_do_coco": "Penha do Coco", "bananal": "Bananal", "agua_limpa": "Água Limpa"}
CAMPOS_ANALISE = ("vazao_ls", "turbidez_bruta", "turbidez_filtrada", "turbidez_tratada", "ph_bruta", "ph_tratada",
                  "sulfato_dosagem", "cloro_dosagem", "cloro_residual", "cor_bruta", "cor_tratada")


def _app():
    return MDApp.get_running_app()


def _enviar(tipo, payload):
    api = _app().api
    if tipo == "analise":
        api.enviar_analise(payload)
    elif tipo == "lavagem":
        api.enviar_lavagem(payload)
    else:
        raise ApiError(f"Tipo de item desconhecido: {tipo}")


class TelaLogin(TelaLoginBase):
    tipos_aceitos = ("operador_eta",)

    def ao_logar(self):
        self.manager.current = "home"


class TelaHome(Screen):
    def on_pre_enter(self):
        self.atualizar()
        self._evento = Clock.schedule_interval(lambda dt: self.atualizar(), 30)

    def on_leave(self):
        if getattr(self, "_evento", None):
            self._evento.cancel()

    def _ultima_local(self):
        try:
            with open(os.path.join(_app().pasta_dados, "ultima_analise.txt")) as f:
                return datetime.fromisoformat(f.read().strip())
        except (OSError, ValueError):
            return None

    def atualizar(self):
        app = _app()
        api = app.api
        self.ids.cab.titulo = api.nome or ""
        self.ids.cab.subtitulo = f"Operador de ETA · {LOCALIDADE_LABEL.get(api.localidade, api.localidade or '—')}"
        pend = fila_local.contar(app.pasta_dados)
        self.ids.pendentes.text = (f"{pend} lançamento(s) aguardando envio" if pend else "Tudo enviado")
        self.ids.pendentes.text_color = app.c_ambar if pend else app.c_ok
        ult = self._ultima_local()
        if ult is None:
            self.ids.prox_titulo.text = "Nenhuma análise registrada neste aparelho"
            self.ids.prox_texto.text = "Faça a primeira análise do turno."
            self.ids.prox_texto.text_color = app.c_texto
        else:
            prox = ult + timedelta(hours=INTERVALO_H)
            falta = prox - datetime.now()
            self.ids.prox_titulo.text = f"Última análise: {ult:%d/%m %H:%M}"
            if falta.total_seconds() > 0:
                m = int(falta.total_seconds() // 60)
                self.ids.prox_texto.text = f"Próxima em {m // 60}h{m % 60:02d} (às {prox:%H:%M})"
                self.ids.prox_texto.text_color = app.c_ok
            else:
                m = int(-falta.total_seconds() // 60)
                self.ids.prox_texto.text = f"ATRASADA há {m // 60}h{m % 60:02d} (devia ser às {prox:%H:%M})"
                self.ids.prox_texto.text_color = app.c_vermelho
        if pend:
            self.sincronizar(silencioso=True)

    def sincronizar(self, silencioso=False):
        app = _app()

        def tarefa():
            return fila_local.sincronizar(app.pasta_dados, _enviar)

        def ok(res):
            enviados, rej, restam = res
            if rej:
                app.aviso(f"{rej} lançamento(s) foram recusados pelo servidor e guardados em 'Recusados'. Veja o histórico.", "Atenção")
            elif enviados and not silencioso:
                app.aviso(f"{enviados} lançamento(s) enviado(s).", "Sincronizado")
            elif not silencioso and restam:
                app.aviso("Sem conexão com o servidor. Os lançamentos continuam guardados no aparelho.")
            pend = fila_local.contar(app.pasta_dados)
            self.ids.pendentes.text = f"{pend} lançamento(s) aguardando envio" if pend else "Tudo enviado"
            self.ids.pendentes.text_color = app.c_ambar if pend else app.c_ok

        rodar_em_background(tarefa, ok, lambda e: None if silencioso else app.aviso(str(e)))

    def trocar_senha(self):
        self.manager.get_screen("trocar_senha").abrir(obrigatoria=False, voltar_para="home")
        self.manager.current = "trocar_senha"

    def sair(self):
        app = _app()
        app.encerrar_sessao()
        app.api = None
        self.manager.current = "login"


class TelaAnalise(Screen):
    def on_pre_enter(self):
        for c in CAMPOS_ANALISE + ("observacoes",):
            self.ids[c].text = ""
        self.ids.msg.text = ""
        self.ids.hora.text = f"Coleta: {datetime.now():%d/%m/%Y %H:%M}"
        self._hora = agora_iso()

    def registrar(self):
        app = _app()
        dados = {"coletado_em": self._hora}
        try:
            for c in CAMPOS_ANALISE:
                dados[c] = numero(self.ids[c].text)
        except ValueError:
            self.ids.msg.text = "Há um campo com valor que não é número."
            return
        dados["observacoes"] = self.ids.observacoes.text.strip() or None
        if all(dados[c] is None for c in CAMPOS_ANALISE):
            self.ids.msg.text = "Preencha ao menos um parâmetro."
            return
        erros = regras_locais.plausivel(dados)
        if erros:
            self.ids.msg.text = " ".join(erros)
            return
        alertas_locais = regras_locais.avaliar(dados)
        self.ids.msg.text = "Enviando..."

        def enviar():
            try:
                return ("enviado", app.api.enviar_analise(dados))
            except (ErroConexao,):
                fila_local.enfileirar(app.pasta_dados, "analise", dados)
                return ("fila", None)

        def ok(res):
            estado, resp = res
            with open(os.path.join(app.pasta_dados, "ultima_analise.txt"), "w") as f:
                f.write(self._hora)
            if estado == "enviado":
                alertas = json.loads(resp["alertas"]) if resp.get("alertas") else []
                msg = "Análise registrada." + ("\n\nATENÇÃO:\n- " + "\n- ".join(alertas) if alertas else "\n\nTodos os parâmetros dentro dos limites.")
            else:
                msg = "Sem internet: análise guardada no aparelho e será enviada sozinha quando houver sinal."
                if alertas_locais:
                    msg += "\n\nATENÇÃO:\n- " + "\n- ".join(alertas_locais)
            app.aviso(msg, "Registrada")
            self.manager.current = "home"

        def erro(e):
            # ErroSessao/validação: NÃO perde o que foi digitado
            self.ids.msg.text = str(e)

        rodar_em_background(enviar, ok, erro)


class TelaLavagem(Screen):
    def on_pre_enter(self):
        self.ids.tempo.text = self.ids.volume.text = self.ids.msg.text = ""
        self._hora = agora_iso()
        self.ids.hora.text = f"Hora: {datetime.now():%d/%m/%Y %H:%M}"

    def registrar(self):
        app = _app()
        try:
            dados = {"hora": self._hora, "tempo_gasto_min": numero(self.ids.tempo.text), "volume_gasto": numero(self.ids.volume.text)}
        except ValueError:
            self.ids.msg.text = "Valor inválido."
            return
        if dados["tempo_gasto_min"] is None and dados["volume_gasto"] is None:
            self.ids.msg.text = "Informe o tempo ou o volume."
            return

        def enviar():
            try:
                app.api.enviar_lavagem(dados)
                return "enviado"
            except ErroConexao:
                fila_local.enfileirar(app.pasta_dados, "lavagem", dados)
                return "fila"

        def ok(estado):
            app.aviso("Lavagem registrada." if estado == "enviado" else "Sem internet: guardada no aparelho para envio automático.")
            self.manager.current = "home"

        rodar_em_background(enviar, ok, lambda e: setattr(self.ids.msg, "text", str(e)))


class TelaHistorico(Screen):
    def on_pre_enter(self):
        app = _app()
        lista = self.ids.lista
        lista.clear_widgets()
        for r in fila_local.listar_rejeitados(app.pasta_dados):
            lista.add_widget(TwoLineListItem(text=f"RECUSADO · {r['tipo']} · {r['criado_em'][:16].replace('T', ' ')}", secondary_text=r["motivo"]))
        for it in fila_local.listar(app.pasta_dados):
            lista.add_widget(TwoLineListItem(text=f"Aguardando envio · {it['tipo']}", secondary_text=it["criado_em"][:16].replace("T", " ")))

        def ok(analises):
            for w in [w for w in lista.children if getattr(w, "_do_servidor", False)]:
                lista.remove_widget(w)
            for a in analises:
                alertas = json.loads(a["alertas"]) if a.get("alertas") else []
                item = TwoLineListItem(
                    text=f"{a['coletado_em'][:16].replace('T', ' ')} · {'FORA DO LIMITE' if a.get('conforme') is False else 'OK'}",
                    secondary_text="; ".join(alertas) if alertas else f"Cloro residual: {a.get('cloro_residual') if a.get('cloro_residual') is not None else '—'}")
                item._do_servidor = True
                lista.add_widget(item)

        rodar_em_background(app.api.minhas_analises, ok, lambda e: lista.add_widget(TwoLineListItem(text="Sem conexão", secondary_text="Mostrando só o que está no aparelho")))


class OperadorEtaApp(AppSiga):
    title = "SIGA · Operador de ETA"
    api = None

    def criar_api(self):
        return ApiClient(self.url_api)

    def build(self):
        self.nome_app = "SIGA · Operador de ETA"
        with open(os.path.join(self.pasta_app, "telas_operador_eta.kv"), encoding="utf-8") as f:
            return self.carregar_base(f.read())


if __name__ == "__main__":
    OperadorEtaApp().run()
