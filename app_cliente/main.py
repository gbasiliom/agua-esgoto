from kivy.config import Config
# Bug conhecido do Kivy no Windows: o provedor de caneta (wm_pen) derruba o
# app em algumas máquinas. Config.set não bastava — precisa remover a opção
# de verdade, tanto da memória quanto do arquivo salvo em disco.
for _opcao in ("wm_pen", "wm_touch"):
    try:
        Config.remove_option("input", _opcao)
    except Exception:
        pass
Config.write()

from kivy.core.window import Window
from kivy.utils import platform
# No PC, sem isso a janela abre no formato de monitor (larga e baixa) e o
# layout — desenhado pra celular (estreito e alto) — fica com espaço vazio
# enorme em cima. CORRIGIDO: isso NÃO é ignorado no Android de verdade (a
# suposição original estava errada) — se aplicado lá, o app renderiza num
# quadradinho de 420x760 PIXELS (minúsculo numa tela de celular real, que
# tem 1080x2400+), em vez de tela cheia. Por isso só aplica no PC.
if platform not in ("android", "ios"):
    Window.size = (420, 760)

import os
import datetime
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.metrics import dp

from kivy.lang import Builder
import kivymd
if not kivymd.__version__.startswith("1.2"):
    print(f"""
❌ Versão errada do KivyMD detectada: {kivymd.__version__}
   Este app foi construído pra rodar com a versão 1.2.0 — a 2.0 (dev/master)
   reorganizou vários componentes (listas, botões, barra superior) de um
   jeito incompatível, então o app quebra na hora de abrir.

   Isso geralmente acontece quando o venv PRÓPRIO desse projeto não foi
   ativado, e o Python acaba usando o Python global da sua máquina (que
   pode ter outra versão do KivyMD instalada, de outro projeto).

   Solução — dentro da pasta app_cliente:
     venv\\Scripts\\activate
     python main.py

   Se mesmo com o venv ativado continuar aparecendo essa mensagem, rode:
     pip install kivymd==1.2.0
""")
    import sys
    sys.exit(1)

from kivymd.app import MDApp
from kivymd.uix.list import TwoLineListItem, OneLineListItem

from api_client import ApiClient, ApiError
from base_app import AppSiga, TelaLoginBase
from async_helper import rodar_em_background

PASTA_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


class TelaSplash(Screen):
    def on_enter(self):
        Clock.schedule_once(self.ir_para_login, 10.5)

    def ir_para_login(self, dt):
        self.manager.current = "login"

TIPO_LABEL = {
    "vazamento": "Vazamento",
    "manutencao": "Manutenção",
    "religacao": "Religação",
    "vistoria": "Vistoria",
    "outro": "Outro",
}

STATUS_LABEL = {
    "aberto": "Aberto — aguardando atendimento",
    "atribuido": "Atribuído a um técnico",
    "em_andamento": "Técnico a caminho / em andamento",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
}


def mostrar_mensagem(texto, titulo="Aviso"):
    popup = Popup(
        title=titulo,
        content=Label(text=texto, text_size=(280, None), halign="center"),
        size_hint=(0.85, 0.35),
        auto_dismiss=True,
    )
    popup.open()
    Clock.schedule_once(lambda dt: popup.dismiss(), 3.5)


class TelaLogin(TelaLoginBase):
    tipos_aceitos = ("cliente",)
    permite_cadastro = True

    def ao_logar(self):
        MDApp.get_running_app().ir_para_tela_certa()


class TelaCadastro(Screen):
    def criar_conta(self, nome, email, telefone, senha, confirmar_senha):
        app = MDApp.get_running_app()
        if not nome or not email or not senha:
            mostrar_mensagem("Preencha nome, e-mail e senha")
            return
        if "@" not in email or "." not in email.split("@")[-1]:
            mostrar_mensagem("Informe um e-mail válido — é por ele que você recupera a senha")
            return
        if senha != confirmar_senha:
            mostrar_mensagem("As senhas não são iguais")
            return

        self.ids.botao_criar.disabled = True
        self.ids.botao_criar.text = "Criando..."
        api = app.criar_api()

        def sucesso(_):
            app.api = api
            self.ids.botao_criar.disabled = False
            self.ids.botao_criar.text = "CRIAR CONTA"
            for campo in ("campo_senha", "campo_confirmar"):
                self.ids[campo].text = ""
            mostrar_mensagem("Conta criada! Agora complete seu endereço.")
            self.manager.get_screen("perfil").preencher_nome(nome.strip())
            self.manager.current = "perfil"

        def erro(e):
            self.ids.botao_criar.disabled = False
            self.ids.botao_criar.text = "CRIAR CONTA"
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao criar conta")

        rodar_em_background(lambda: api.registrar(nome.strip(), email.strip(), (telefone or "").strip() or None, senha), sucesso, erro)


CHAVE_LOCALIDADE = {"Sede": "sede", "Penha do Coco": "penha_do_coco", "Bananal": "bananal", "Água Limpa": "agua_limpa"}


def tem_hidrometro(localidade):
    """Só a Sede tem hidrômetro (leitura mensal e fatura)."""
    return localidade in (None, "sede")


class TelaPerfil(Screen):
    def preencher_nome(self, nome):
        self.ids.campo_nome.text = nome

    def ao_trocar_localidade(self, texto):
        """Fora da Sede não há hidrômetro: o campo some."""
        tem = tem_hidrometro(CHAVE_LOCALIDADE.get(texto, texto))
        for w in (self.ids.rotulo_hidrometro, self.ids.campo_hidrometro):
            w.opacity = 1 if tem else 0
            w.disabled = not tem
            w.height = (w.texture_size[1] + dp(4) if w is self.ids.rotulo_hidrometro else dp(56)) if tem else 0
        if not tem:
            self.ids.campo_hidrometro.text = ""

    def salvar(self, nome, endereco, bairro, cidade, hidrometro, categoria, localidade):
        app = MDApp.get_running_app()
        if not nome or not endereco:
            mostrar_mensagem("Nome e endereço são obrigatórios")
            return
        localidade = CHAVE_LOCALIDADE.get(localidade, localidade)
        if not tem_hidrometro(localidade):
            hidrometro = ""

        self.ids.botao_salvar.disabled = True
        self.ids.botao_salvar.text = "Salvando..."

        def sucesso(cadastro):
            app.meu_cadastro_atual = cadastro
            self.ids.botao_salvar.disabled = False
            self.ids.botao_salvar.text = "SALVAR"
            mostrar_mensagem("Cadastro completo! Aguarde a aprovação do operador pra abrir chamados.")
            self.manager.current = "home"

        def erro(e):
            self.ids.botao_salvar.disabled = False
            self.ids.botao_salvar.text = "SALVAR"
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao salvar cadastro")

        rodar_em_background(
            lambda: app.api.criar_cadastro(nome, endereco, bairro, cidade, hidrometro, categoria or "residencial", localidade),
            sucesso, erro,
        )


class TelaHome(Screen):
    def on_pre_enter(self):
        app = MDApp.get_running_app()
        cadastro = getattr(app, "meu_cadastro_atual", None)

        hora = datetime.datetime.now().hour
        if hora < 12:
            saudacao = "Bom dia"
        elif hora < 18:
            saudacao = "Boa tarde"
        else:
            saudacao = "Boa noite"

        nome = cadastro.get("nome") if cadastro else None
        primeiro_nome = nome.split()[0] if nome else ""
        self.ids.texto_saudacao.text = f"{saudacao}, {primeiro_nome}" if primeiro_nome else saudacao
        partes = [(cadastro or {}).get("endereco"), "Hidrômetro " + cadastro["hidrometro"] if cadastro and cadastro.get("hidrometro") and tem_hidrometro(cadastro.get("localidade")) else None]
        self.ids.texto_endereco.text = " · ".join(p for p in partes if p)

        # Só a Sede tem hidrômetro: fora dela, leitura e faturas não aparecem.
        tem = tem_hidrometro((cadastro or {}).get("localidade"))
        grade = self.ids.grade_acoes
        for w in (self.ids.card_leitura, self.ids.card_faturas):
            if w.parent is not None:
                grade.remove_widget(w)
        if tem:
            grade.add_widget(self.ids.card_leitura)
            grade.add_widget(self.ids.card_faturas)

        if cadastro and cadastro.get("status_cadastro") == "pendente":
            self.ids.aviso_pendente.text = "Seu cadastro está aguardando aprovação do operador. Assim que for aprovado, você já poderá abrir chamados."
        else:
            self.ids.aviso_pendente.text = ""

        def sucesso(info):
            if not info.get("aplica", True):
                self.ids.aviso_leitura.text = ""
            elif not info["enviada"]:
                self.ids.aviso_leitura.text = f"A leitura do hidrômetro de {info['competencia']} ainda não foi enviada!"
            elif info["status"] == "pendente":
                self.ids.aviso_leitura.text = "Leitura enviada — aguardando validação do operador."
            elif info["status"] == "rejeitada":
                self.ids.aviso_leitura.text = "Atenção: sua última leitura foi rejeitada. Confira em 'Informar leitura'."
            else:
                self.ids.aviso_leitura.text = ""

        def erro(e):
            self.ids.aviso_leitura.text = ""

        if tem:
            rodar_em_background(app.api.pendente_mes_leitura, sucesso, erro)
        else:
            self.ids.aviso_leitura.text = ""

    def trocar_senha(self):
        self.manager.get_screen("trocar_senha").abrir(obrigatoria=False, voltar_para="home")
        self.manager.current = "trocar_senha"

    def sair(self):
        app = MDApp.get_running_app()
        app.encerrar_sessao()
        app.api = None
        app.meu_cadastro_atual = None
        self.manager.current = "login"

    def ir_abrir_chamado(self):
        self.manager.current = "abrir_chamado"

    def ir_leitura_hidrometro(self):
        self.manager.current = "leitura_hidrometro"

    def ir_minhas_faturas(self):
        self.manager.get_screen("minhas_faturas").carregar()
        self.manager.current = "minhas_faturas"

    def ir_meus_chamados(self):
        self.manager.get_screen("meus_chamados").carregar()
        self.manager.current = "meus_chamados"


MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


class TelaLeituraHidrometro(Screen):
    caminho_foto = None

    def on_pre_enter(self):
        app = MDApp.get_running_app()
        self.caminho_foto = None
        self.ids.campo_valor.text = ""
        self.ids.texto_foto.text = "Nenhuma foto tirada ainda"

        agora = datetime.datetime.now()
        self.ids.valor_mes_referencia.text = f"{MESES_PT[agora.month - 1]}/{agora.year}"

        ultimo_dia = (datetime.datetime(agora.year, agora.month % 12 + 1, 1) - datetime.timedelta(days=1)).day
        self.ids.valor_periodo.text = f"01/{agora.month:02d} a {ultimo_dia}/{agora.month:02d}"

        def sucesso(dados):
            if dados.get("valor") is not None:
                self.ids.valor_ultima_leitura.text = f"{dados['valor']:.0f}"
            else:
                self.ids.valor_ultima_leitura.text = "—"

        def erro(e):
            self.ids.valor_ultima_leitura.text = "—"

        rodar_em_background(app.api.ultima_leitura, sucesso, erro)

    def tirar_foto(self):
        """No celular: câmera nativa de verdade. No PC: seletor de arquivo (modo teste)."""
        from plyer import camera

        app = MDApp.get_running_app()
        caminho = os.path.join(app.user_data_dir, f"leitura_{datetime.datetime.now().timestamp()}.jpg")

        def ao_terminar(caminho_salvo):
            self.caminho_foto = caminho_salvo
            self.ids.texto_foto.text = "Foto adicionada ✓"

        try:
            camera.take_picture(filename=caminho, on_complete=lambda path: ao_terminar(caminho))
        except NotImplementedError:
            from plyer import filechooser

            def ao_selecionar(selecao):
                if selecao:
                    ao_terminar(selecao[0])
                else:
                    mostrar_mensagem("Nenhuma foto selecionada")

            try:
                filechooser.open_file(
                    title="Escolha uma foto do hidrômetro (modo teste no PC)",
                    filters=[("Imagens", "*.jpg", "*.jpeg", "*.png")],
                    on_selection=ao_selecionar,
                )
            except Exception:
                mostrar_mensagem("Não foi possível abrir o seletor de arquivos")

    def enviar(self, valor_texto):
        app = MDApp.get_running_app()
        if not valor_texto.strip():
            mostrar_mensagem("Informe o número que está no hidrômetro")
            return
        try:
            valor = float(valor_texto.replace(",", "."))
        except ValueError:
            mostrar_mensagem("Digite só números")
            return
        if not self.caminho_foto:
            mostrar_mensagem("Tire uma foto do hidrômetro antes de enviar")
            return

        self.ids.botao_enviar.disabled = True
        self.ids.botao_enviar.text = "Enviando..."

        def sucesso(_):
            self.ids.botao_enviar.disabled = False
            self.ids.botao_enviar.text = "ENVIAR LEITURA"
            mostrar_mensagem("Leitura enviada! Aguarde a validação do operador.")
            self.manager.current = "home"

        def erro(e):
            self.ids.botao_enviar.disabled = False
            self.ids.botao_enviar.text = "ENVIAR LEITURA"
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao enviar leitura")

        rodar_em_background(lambda: app.api.enviar_leitura(valor, self.caminho_foto), sucesso, erro)


class TelaAbrirChamado(Screen):
    def abrir(self, tipo, descricao, prioridade):
        app = MDApp.get_running_app()
        if tipo == "Selecione":
            mostrar_mensagem("Selecione o tipo de problema")
            return
        if prioridade == "Selecione":
            mostrar_mensagem("Selecione a prioridade")
            return
        if not descricao.strip():
            mostrar_mensagem("Descreva o problema")
            return

        self.ids.botao_abrir.disabled = True
        self.ids.botao_abrir.text = "Enviando..."

        def sucesso(chamado):
            self.ids.botao_abrir.disabled = False
            self.ids.botao_abrir.text = "ABRIR CHAMADO"
            mostrar_mensagem(f"Chamado #{chamado['id']} aberto com sucesso!")
            self.ids.campo_descricao.text = ""
            self.ids.spinner_tipo.text = "Selecione"
            self.ids.spinner_prioridade.text = "Selecione"
            self.manager.current = "home"

        def erro(e):
            self.ids.botao_abrir.disabled = False
            self.ids.botao_abrir.text = "ABRIR CHAMADO"
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao abrir chamado")

        rodar_em_background(lambda: app.api.abrir_chamado(tipo, descricao.strip(), prioridade), sucesso, erro)


class TelaMeusChamados(Screen):
    def carregar(self):
        app = MDApp.get_running_app()
        lista_widget = self.ids.lista_meus_chamados
        lista_widget.clear_widgets()
        lista_widget.add_widget(OneLineListItem(text="Carregando..."))

        def sucesso(chamados):
            lista_widget.clear_widgets()
            if not chamados:
                lista_widget.add_widget(OneLineListItem(text="Você ainda não abriu nenhum chamado"))
                return
            for chamado in chamados:
                texto_principal = f"#{chamado['id']} — {TIPO_LABEL.get(chamado['tipo'], chamado['tipo'])}"
                texto_secundario = STATUS_LABEL.get(chamado["status"], chamado["status"])
                lista_widget.add_widget(TwoLineListItem(text=texto_principal, secondary_text=texto_secundario))

        def erro(e):
            lista_widget.clear_widgets()
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao carregar chamados")

        rodar_em_background(app.api.meus_chamados, sucesso, erro)


class TelaMinhasFaturas(Screen):
    def carregar(self):
        app = MDApp.get_running_app()
        lista_widget = self.ids.lista_minhas_faturas
        lista_widget.clear_widgets()
        lista_widget.add_widget(OneLineListItem(text="Carregando..."))

        def sucesso(faturas):
            lista_widget.clear_widgets()
            if not faturas:
                lista_widget.add_widget(OneLineListItem(text="Você ainda não tem faturas geradas"))
                return
            for fatura in faturas:
                status_label = {"aberto": "Em aberto", "pago": "Paga", "vencido": "Vencida"}.get(
                    fatura["status"], fatura["status"]
                )
                texto_principal = f"{fatura['competencia']} — R$ {fatura['valor_total']:.2f}"
                texto_secundario = f"{status_label} — consumo {fatura['consumo_m3']:.0f}m³"
                lista_widget.add_widget(TwoLineListItem(text=texto_principal, secondary_text=texto_secundario))

        def erro(e):
            lista_widget.clear_widgets()
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao carregar faturas")

        rodar_em_background(app.api.minhas_faturas, sucesso, erro)


class ClienteApp(AppSiga):
    title = "SIGA · Cliente"
    api = None
    meu_cadastro_atual = None

    def on_start(self):
        # Android 6+ exige pedir a permissão da câmera/arquivos na hora (só declarar no buildozer.spec não basta).
        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.CAMERA, Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
            except Exception:
                pass

    def criar_api(self):
        return ApiClient(self.url_api)

    def build(self):
        self.nome_app = "Área do morador"
        with open(os.path.join(self.pasta_app, "telas_cliente.kv"), encoding="utf-8") as f:
            raiz = self.carregar_base(f.read())
        raiz.current = "splash"
        return raiz

    def ir_para_tela_certa(self):
        """Depois do login: se ainda não completou o cadastro (endereço), manda pra lá."""
        def buscar_cadastro():
            return self.api.meu_cadastro()

        def sucesso(cadastro):
            self.meu_cadastro_atual = cadastro
            self.root.current = "perfil" if cadastro is None else "home"

        def erro(e):
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao verificar cadastro")

        rodar_em_background(buscar_cadastro, sucesso, erro)


if __name__ == "__main__":
    ClienteApp().run()
