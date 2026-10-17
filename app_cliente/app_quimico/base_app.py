"""Peças comuns aos apps de campo (Operador de ETA e Químico)."""
import os
from datetime import datetime

from kivy.lang import Builder
from kivy.properties import StringProperty, ListProperty
from kivy.uix.screenmanager import Screen
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton

import tema
import config
from api_base import ApiError, ErroConexao
from async_helper import rodar_em_background


class AppSiga(MDApp):
    """Classe-base: cores, brasão, endereço do servidor, diálogos."""
    nome_app = StringProperty("")
    url_api = StringProperty("")
    brasao = StringProperty("")
    c_marinho = ListProperty(tema.AZUL_MARINHO)
    c_escuro = ListProperty(tema.AZUL_ESCURO)
    c_claro = ListProperty(tema.AZUL_CLARO)
    c_texto = ListProperty(tema.CINZA_TEXTO)
    c_ok = ListProperty(tema.VERDE_OK)
    c_ambar = ListProperty(tema.AMBAR)
    c_vermelho = ListProperty(tema.VERMELHO)

    @property
    def pasta_app(self):
        return os.path.dirname(os.path.abspath(__file__))  # a cópia de base_app.py fica na pasta do app

    @property
    def pasta_dados(self):
        return self.user_data_dir

    def carregar_base(self, kv_do_app):
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.theme_style = "Light"
        self.brasao = tema.caminho_brasao(self.pasta_app)
        self.url_api = config.carregar_url(self.pasta_dados)
        Builder.load_file(os.path.join(self.pasta_app, "kv_comum.kv"))
        return Builder.load_string(kv_do_app)

    def aviso(self, texto, titulo="Aviso"):
        d = MDDialog(title=titulo, text=texto, buttons=[MDFlatButton(text="OK", on_release=lambda *_: d.dismiss())])
        d.open()


class TelaLoginBase(Screen):
    """Subclasse define `tipos_aceitos` e `ao_logar(self)`."""
    tipos_aceitos = ()

    def alternar_servidor(self):
        campo, botao = self.ids.servidor, self.ids.salvar_servidor
        mostrar = campo.disabled
        campo.disabled = botao.disabled = not mostrar
        campo.opacity = botao.opacity = 1 if mostrar else 0
        campo.height = dp(56) if mostrar else 0
        botao.height = dp(40) if mostrar else 0
        if mostrar:
            campo.text = MDApp.get_running_app().url_api

    def salvar_servidor(self):
        app = MDApp.get_running_app()
        try:
            app.url_api = config.salvar_url(app.pasta_dados, self.ids.servidor.text)
        except ValueError as e:
            self.ids.msg.text = str(e)
            return
        self.ids.msg.text = ""
        self.alternar_servidor()

    def entrar(self):
        app = MDApp.get_running_app()
        ident, senha = self.ids.ident.text.strip(), self.ids.senha.text
        if not ident or not senha:
            self.ids.msg.text = "Informe telefone/e-mail e senha."
            return
        self.ids.msg.text = "Entrando..."
        api = app.criar_api()

        def sucesso(_):
            app.api = api
            self.ids.senha.text = ""
            self.ids.msg.text = ""
            self.ao_logar()

        def erro(e):
            self.ids.msg.text = str(e)

        rodar_em_background(lambda: api.login(ident, senha, self.tipos_aceitos), sucesso, erro)

    def ao_logar(self):
        raise NotImplementedError


def numero(texto):
    """'' -> None; aceita vírgula decimal. Levanta ValueError se não for número."""
    texto = (texto or "").strip().replace(",", ".")
    return float(texto) if texto else None


def agora_iso():
    return datetime.now().replace(microsecond=0).isoformat()
