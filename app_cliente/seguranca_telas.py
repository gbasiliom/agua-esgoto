"""Telas de segurança compartilhadas pelos apps Kivy (técnico, cliente, químico, operador de ETA):
  - esqueci_senha  → pede o e-mail/telefone e dispara o código de 6 dígitos por e-mail
  - esqueci_codigo → digita o código e define a nova senha
  - trocar_senha   → troca de senha logado; é obrigatória depois de senha provisória/fraca
O app só precisa chamar `registrar_telas(sm)` e ter `app.url_api`."""
import time

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivymd.app import MDApp
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog

import fluxo_senha
from async_helper import rodar_em_background

ESPERA_REENVIO_S = 45


def _app():
    return MDApp.get_running_app()


def _aviso(texto, titulo="Pronto", ao_fechar=None):
    def fechar(*_):
        d.dismiss()
        if ao_fechar:
            ao_fechar()
    d = MDDialog(title=titulo, text=texto, auto_dismiss=False, buttons=[MDFlatButton(text="OK", on_release=fechar)])
    d.open()


def _msg(tela, texto, ok=False):
    app = _app()
    lbl = tela.ids.msg
    lbl.text = texto
    lbl.text_color = app.c_ok if ok else app.c_vermelho


class TelaEsqueciSenha(Screen):
    def on_pre_enter(self):
        self.ids.msg.text = ""
        self.ids.botao.disabled = False

    def voltar(self):
        self.manager.current = "login"

    def enviar(self):
        ident = self.ids.ident.text.strip()
        if not ident:
            _msg(self, "Informe o e-mail ou o telefone do seu cadastro.")
            return
        self.ids.botao.disabled = True
        _msg(self, "Enviando…", ok=True)

        def sucesso(texto):
            self.ids.botao.disabled = False
            self.manager.get_screen("esqueci_codigo").iniciar(ident, texto)
            self.manager.current = "esqueci_codigo"

        def erro(e):
            self.ids.botao.disabled = False
            _msg(self, str(e))

        rodar_em_background(lambda: fluxo_senha.esqueci_senha(_app().url_api, ident), sucesso, erro)


class TelaEsqueciCodigo(Screen):
    identificador = ""
    _liberar_reenvio_em = 0
    _relogio = None

    def iniciar(self, identificador, texto_servidor=""):
        self.identificador = identificador
        for campo in ("codigo", "nova", "nova2"):
            self.ids[campo].text = ""
        self.ids.explicacao.text = ("Se existir cadastro com esse e-mail ou telefone, enviamos um código de 6 dígitos para o e-mail da conta. "
                                    "Olhe também a caixa de spam.")
        self.ids.msg.text = ""
        self.ids.botao.disabled = False
        self._liberar_reenvio_em = time.monotonic() + ESPERA_REENVIO_S
        if self._relogio:
            self._relogio.cancel()
        self._relogio = Clock.schedule_interval(lambda dt: self._atualizar_reenvio(), 1)
        self._atualizar_reenvio()

    def on_leave(self, *args):
        if self._relogio:
            self._relogio.cancel()
            self._relogio = None

    def _atualizar_reenvio(self):
        falta = int(self._liberar_reenvio_em - time.monotonic()) + 1
        if falta > 0:
            self.ids.reenviar.text = f"Reenviar código ({falta}s)"
            self.ids.reenviar.disabled = True
        else:
            self.ids.reenviar.text = "Reenviar código"
            self.ids.reenviar.disabled = False

    def reenviar(self):
        self.ids.reenviar.disabled = True
        _msg(self, "Enviando novo código…", ok=True)

        def sucesso(_):
            self._liberar_reenvio_em = time.monotonic() + ESPERA_REENVIO_S
            _msg(self, "Novo código enviado. O anterior deixou de valer.", ok=True)

        def erro(e):
            _msg(self, str(e))

        rodar_em_background(lambda: fluxo_senha.esqueci_senha(_app().url_api, self.identificador), sucesso, erro)

    def voltar(self):
        self.manager.current = "esqueci_senha"

    def redefinir(self):
        codigo, nova, nova2 = self.ids.codigo.text.strip(), self.ids.nova.text, self.ids.nova2.text
        if len(codigo) != 6:
            _msg(self, "O código tem 6 dígitos.")
            return
        faltas = fluxo_senha.problemas_senha(nova, nova2)
        if faltas:
            _msg(self, "As duas senhas precisam ser iguais." if faltas == ["as duas senhas iguais"] else fluxo_senha.texto_problemas(faltas))
            return
        self.ids.botao.disabled = True
        _msg(self, "Salvando…", ok=True)

        def sucesso(texto):
            self.ids.botao.disabled = False
            for campo in ("codigo", "nova", "nova2"):
                self.ids[campo].text = ""
            _aviso(texto, "Senha redefinida", lambda: setattr(self.manager, "current", "login"))

        def erro(e):
            self.ids.botao.disabled = False
            _msg(self, str(e))

        rodar_em_background(lambda: fluxo_senha.redefinir_senha(_app().url_api, self.identificador, codigo, nova), sucesso, erro)


class TelaTrocarSenha(Screen):
    """`abrir(obrigatoria, ao_concluir, voltar_para)` antes de mostrar a tela."""
    obrigatoria = False
    ao_concluir = None
    voltar_para = "login"

    def abrir(self, obrigatoria=False, ao_concluir=None, voltar_para="login"):
        self.obrigatoria, self.ao_concluir, self.voltar_para = obrigatoria, ao_concluir, voltar_para
        for campo in ("atual", "nova", "nova2"):
            self.ids[campo].text = ""
        self.ids.msg.text = ""
        self.ids.botao.disabled = False
        self.ids.explicacao.text = (
            "Por segurança, defina uma nova senha antes de continuar. A senha atual é provisória ou fraca demais."
            if obrigatoria else "Escolha uma senha nova. Os outros aparelhos conectados com esta conta serão desconectados."
        )
        self.ids.cancelar.opacity = 0 if obrigatoria else 1
        self.ids.cancelar.disabled = obrigatoria
        self.ids.cancelar.height = 0 if obrigatoria else self.ids.botao.height

    def cancelar(self):
        if not self.obrigatoria:
            self.manager.current = self.voltar_para

    def sair_da_conta(self):
        """Senha obrigatória não pode ser pulada: a única saída é sair da conta."""
        fluxo_senha.sair(_app().url_api)
        self.manager.current = "login"

    def salvar(self):
        atual, nova, nova2 = self.ids.atual.text, self.ids.nova.text, self.ids.nova2.text
        if not atual:
            _msg(self, "Digite a senha atual.")
            return
        faltas = fluxo_senha.problemas_senha(nova, nova2)
        if faltas:
            _msg(self, "As duas senhas precisam ser iguais." if faltas == ["as duas senhas iguais"] else fluxo_senha.texto_problemas(faltas))
            return
        if nova == atual:
            _msg(self, "A nova senha precisa ser diferente da atual.")
            return
        self.ids.botao.disabled = True
        _msg(self, "Salvando…", ok=True)

        def sucesso(_):
            self.ids.botao.disabled = False
            for campo in ("atual", "nova", "nova2"):
                self.ids[campo].text = ""

            def seguir():
                if self.ao_concluir:
                    self.ao_concluir()
                else:
                    self.manager.current = self.voltar_para
            _aviso("Senha alterada com sucesso.", "Pronto", seguir)

        def erro(e):
            self.ids.botao.disabled = False
            _msg(self, str(e))

        rodar_em_background(lambda: fluxo_senha.trocar_senha(_app().url_api, atual, nova), sucesso, erro)


def registrar_telas(sm):
    """Adiciona as 3 telas ao ScreenManager do app."""
    sm.add_widget(TelaEsqueciSenha(name="esqueci_senha"))
    sm.add_widget(TelaEsqueciCodigo(name="esqueci_codigo"))
    sm.add_widget(TelaTrocarSenha(name="trocar_senha"))
