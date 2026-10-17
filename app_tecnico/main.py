import os
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

from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.properties import ObjectProperty, StringProperty
from kivy.clock import Clock

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

   Solução — dentro da pasta app_tecnico:
     venv\\Scripts\\activate
     python main.py

   Se mesmo com o venv ativado continuar aparecendo essa mensagem, rode:
     pip install kivymd==1.2.0
""")
    import sys
    sys.exit(1)

from kivymd.app import MDApp
from kivymd.uix.list import OneLineListItem, TwoLineListItem

import json
import datetime
from api_client import ApiClient, ApiError, ErroConexao
from base_app import AppSiga, TelaLoginBase
from async_helper import rodar_em_background
import armazenamento_local as db_local
import sincronizador
import ao_vivo_tecnico as vivo

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
    "atribuido": "Atribuído — aguardando você iniciar",
    "em_andamento": "Em andamento",
}

# Checklist da situação encontrada — ids batem com os do tecnico.kv
CHECKLIST_ITENS = [
    ("chk_vazamento", "Vazamento visível confirmado"),
    ("chk_registro_ok", "Registro/válvula funcionando normalmente"),
    ("chk_tubulacao_dano", "Tubulação com dano visível"),
    ("chk_hidrometro_dano", "Hidrômetro danificado ou violado"),
    ("chk_acesso_liberado", "Acesso ao local estava liberado"),
    ("chk_ja_resolvido", "Problema já havia sido resolvido antes da chegada"),
    ("chk_retorno_necessario", "Necessário retorno com equipe/equipamento adicional"),
]


def mostrar_mensagem(texto, titulo="Aviso"):
    popup = Popup(
        title=titulo,
        content=Label(text=texto, text_size=(280, None), halign="center"),
        size_hint=(0.85, 0.35),
        auto_dismiss=True,
    )
    popup.open()
    Clock.schedule_once(lambda dt: popup.dismiss(), 3.5)


def avisar_novidade(texto, titulo="Novidade"):
    """Aviso que fica mais tempo na tela (8 s) — chamado novo não pode passar despercebido."""
    popup = Popup(
        title=titulo,
        content=Label(text=texto, text_size=(280, None), halign="center"),
        size_hint=(0.85, 0.4),
        auto_dismiss=True,
    )
    popup.open()
    Clock.schedule_once(lambda dt: popup.dismiss(), 8)


class TelaLogin(TelaLoginBase):
    tipos_aceitos = ("tecnico",)

    def ao_logar(self):
        MDApp.get_running_app().iniciar_ao_vivo()
        self.manager.current = "home_tecnico"


TIPO_MANUTENCAO_LABEL = {
    "limpeza_tanque": "Limpeza de tanque",
    "verificacao_cloro": "Verificação de cloro/dosagem",
    "manutencao_bomba": "Manutenção de bomba/equipamento",
    "outro": "Outro",
}


class TelaHomeTecnico(Screen):
    """Painel inicial do técnico — escolhe entre Chamados e Estoque/ETA."""

    def on_pre_enter(self):
        app = MDApp.get_running_app()
        hora = datetime.datetime.now().hour
        saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
        nome = (getattr(app.api, "nome", None) or "").split()
        self.ids.saudacao.text = f"{saudacao}, {nome[0]}" if nome else saudacao

    def ir_chamados(self):
        self.manager.get_screen("lista").carregar()
        self.manager.current = "lista"

    def ir_estoque(self):
        self.manager.get_screen("estoque_tecnico").carregar()
        self.manager.current = "estoque_tecnico"

    def trocar_senha(self):
        self.manager.get_screen("trocar_senha").abrir(obrigatoria=False, voltar_para="home_tecnico")
        self.manager.current = "trocar_senha"

    def sair(self):
        app = MDApp.get_running_app()
        app.parar_ao_vivo()
        app.encerrar_sessao()
        app.api = None
        self.manager.current = "login"


class TelaEstoqueTecnico(Screen):
    itens_catalogo = []

    def carregar(self):
        app = MDApp.get_running_app()
        lista_widget = self.ids.lista_estoque_tecnico
        lista_widget.clear_widgets()
        lista_widget.add_widget(OneLineListItem(text="Carregando..."))
        self.ids.spinner_insumo.values = ["(carregando...)"]
        self.ids.spinner_insumo.text = "(carregando...)"
        self.ids.campo_quantidade_pedido.text = ""

        def sucesso(resultado):
            meu_estoque, catalogo = resultado
            self.itens_catalogo = catalogo
            lista_widget.clear_widgets()

            minimo_por_item = {item["id"]: item["estoque_minimo"] for item in catalogo}
            if not meu_estoque:
                lista_widget.add_widget(OneLineListItem(text="Você ainda não tem nenhum item em mãos"))
            for item in meu_estoque:
                abaixo_do_minimo = item["quantidade"] < minimo_por_item.get(item["item_id"], 0)
                prefixo = "⚠ " if abaixo_do_minimo else ""
                texto = f"{prefixo}{item['nome_item']} — {item['quantidade']:.0f} {item['unidade_medida']}"
                lista_widget.add_widget(OneLineListItem(text=texto))

            nomes_catalogo = [i["nome"] for i in catalogo]
            self.ids.spinner_insumo.values = nomes_catalogo or ["(nenhum item cadastrado)"]
            self.ids.spinner_insumo.text = nomes_catalogo[0] if nomes_catalogo else "(nenhum item cadastrado)"

        def erro(e):
            lista_widget.clear_widgets()
            lista_widget.add_widget(OneLineListItem(text="Estoque indisponível offline"))
            self.ids.spinner_insumo.values = ["(indisponível offline)"]
            self.ids.spinner_insumo.text = "(indisponível offline)"

        def buscar():
            return app.api.meu_estoque(), app.api.catalogo_estoque()

        rodar_em_background(buscar, sucesso, erro)

    def solicitar_insumo(self):
        app = MDApp.get_running_app()
        nome_escolhido = self.ids.spinner_insumo.text
        item = next((i for i in self.itens_catalogo if i["nome"] == nome_escolhido), None)
        if not item:
            mostrar_mensagem("Selecione um insumo válido do catálogo")
            return
        try:
            quantidade = float(self.ids.campo_quantidade_pedido.text.replace(",", "."))
        except ValueError:
            mostrar_mensagem("Digite uma quantidade válida")
            return
        if quantidade <= 0:
            mostrar_mensagem("Quantidade precisa ser maior que zero")
            return

        self.ids.botao_solicitar_insumo.disabled = True
        self.ids.botao_solicitar_insumo.text = "Enviando..."

        def sucesso(_):
            self.ids.botao_solicitar_insumo.disabled = False
            self.ids.botao_solicitar_insumo.text = "Solicitar"
            self.ids.campo_quantidade_pedido.text = ""
            mostrar_mensagem("Solicitação enviada! Aguarde a aprovação do operador.")

        def erro(e):
            self.ids.botao_solicitar_insumo.disabled = False
            self.ids.botao_solicitar_insumo.text = "Solicitar"
            if isinstance(e, ErroConexao):
                mostrar_mensagem("Sem internet — solicitações precisam de conexão (o operador precisa ver na hora).")
            else:
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao solicitar insumo")

        # chamado_id=None: solicitação avulsa, não vinculada a nenhum chamado
        rodar_em_background(lambda: app.api.solicitar_material(item["id"], quantidade, None), sucesso, erro)

    def ir_manutencao_eta(self):
        self.manager.current = "manutencao_eta"

    def ir_analise_eta(self):
        self.manager.current = "analise_eta"

    def ir_lavagem_filtro(self):
        self.manager.current = "lavagem_filtro"

    def ir_minhas_solicitacoes(self):
        self.manager.get_screen("minhas_solicitacoes").carregar()
        self.manager.current = "minhas_solicitacoes"


class TelaManutencaoEta(Screen):
    def on_pre_enter(self):
        self.ids.campo_descricao_manutencao.text = ""
        self.ids.spinner_tipo_manutencao.text = TIPO_MANUTENCAO_LABEL["limpeza_tanque"]

    def registrar(self):
        app = MDApp.get_running_app()
        texto_tipo = self.ids.spinner_tipo_manutencao.text
        tipo = next((k for k, v in TIPO_MANUTENCAO_LABEL.items() if v == texto_tipo), "outro")
        descricao = self.ids.campo_descricao_manutencao.text.strip()

        if not descricao:
            mostrar_mensagem("Descreva o que foi feito na manutenção")
            return

        self.ids.botao_registrar_manutencao.disabled = True
        self.ids.botao_registrar_manutencao.text = "Registrando..."

        def sucesso(_):
            self.ids.botao_registrar_manutencao.disabled = False
            self.ids.botao_registrar_manutencao.text = "Registrar"
            mostrar_mensagem("Manutenção registrada com sucesso!")
            self.manager.current = "estoque_tecnico"

        def erro(e):
            self.ids.botao_registrar_manutencao.disabled = False
            self.ids.botao_registrar_manutencao.text = "Registrar"
            if isinstance(e, ErroConexao):
                mostrar_mensagem("Sem internet — o registro de manutenção precisa de conexão.")
            else:
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao registrar manutenção")

        rodar_em_background(lambda: app.api.registrar_manutencao_eta(tipo, descricao), sucesso, erro)


class TelaMinhasSolicitacoes(Screen):
    def carregar(self):
        app = MDApp.get_running_app()
        lista_widget = self.ids.lista_solicitacoes
        lista_widget.clear_widgets()
        lista_widget.add_widget(OneLineListItem(text="Carregando..."))

        def sucesso(solicitacoes):
            lista_widget.clear_widgets()
            if not solicitacoes:
                lista_widget.add_widget(OneLineListItem(text="Você ainda não fez nenhuma solicitação"))
                return
            for s in solicitacoes:
                if s["status"] == "pendente":
                    status_texto = "Pendente"
                elif s["status"] == "negada":
                    status_texto = "Negada"
                elif s["modo_aprovacao"] == "compra_direta" and not s.get("nota_fiscal_foto"):
                    status_texto = "Autorizada p/ compra — envie a nota fiscal"
                elif s["modo_aprovacao"] == "compra_direta":
                    status_texto = f"Compra direta enviada — R$ {s['valor_compra']:.2f}"
                else:
                    status_texto = "Aprovada (transferência de estoque)"

                texto_principal = f"#{s['id']} — item #{s['item_id']} ({s['quantidade']:.0f})"
                pode_enviar_comprovante = (
                    s["status"] == "aprovada" and s["modo_aprovacao"] == "compra_direta" and not s.get("nota_fiscal_foto")
                )
                item = TwoLineListItem(text=texto_principal, secondary_text=status_texto)
                if pode_enviar_comprovante:
                    item.bind(on_release=lambda x, s=s: self._ir_enviar_comprovante(s))
                lista_widget.add_widget(item)

        def erro(e):
            lista_widget.clear_widgets()
            mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao carregar solicitações")

        rodar_em_background(app.api.minhas_solicitacoes, sucesso, erro)

    def _ir_enviar_comprovante(self, solicitacao):
        tela = self.manager.get_screen("enviar_comprovante")
        tela.preparar(solicitacao)
        self.manager.current = "enviar_comprovante"


class TelaEnviarComprovante(Screen):
    solicitacao = ObjectProperty(None)
    fornecedores = []
    caminho_foto = None

    def preparar(self, solicitacao):
        self.solicitacao = solicitacao
        self.caminho_foto = None
        self.ids.campo_valor_compra.text = ""
        self.ids.texto_foto_nota.text = "Nenhuma foto tirada ainda"
        self.ids.spinner_fornecedor.values = ["(carregando...)"]
        self.ids.spinner_fornecedor.text = "(carregando...)"

        app = MDApp.get_running_app()

        def sucesso(fornecedores):
            self.fornecedores = fornecedores
            nomes = [f["nome"] for f in fornecedores]
            self.ids.spinner_fornecedor.values = nomes or ["(nenhum fornecedor cadastrado)"]
            self.ids.spinner_fornecedor.text = nomes[0] if nomes else "(nenhum fornecedor cadastrado)"

        def erro(e):
            self.ids.spinner_fornecedor.values = ["(indisponível offline)"]
            self.ids.spinner_fornecedor.text = "(indisponível offline)"

        rodar_em_background(app.api.listar_fornecedores, sucesso, erro)

    def tirar_foto_nota(self):
        from plyer import camera

        app = MDApp.get_running_app()
        caminho = os.path.join(app.user_data_dir, f"nota_fiscal_{self.solicitacao['id']}.jpg")

        def ao_terminar(caminho_salvo):
            self.caminho_foto = caminho_salvo
            self.ids.texto_foto_nota.text = "Foto adicionada ✓"

        try:
            camera.take_picture(filename=caminho, on_complete=lambda path: ao_terminar(caminho))
        except NotImplementedError:
            from plyer import filechooser

            def ao_selecionar(selecao):
                if selecao:
                    ao_terminar(selecao[0])

            try:
                filechooser.open_file(
                    title="Escolha uma foto da nota fiscal (modo teste no PC)",
                    filters=[("Imagens", "*.jpg", "*.jpeg", "*.png")],
                    on_selection=ao_selecionar,
                )
            except Exception:
                mostrar_mensagem("Não foi possível abrir o seletor de arquivos")

    def enviar(self):
        app = MDApp.get_running_app()
        nome_escolhido = self.ids.spinner_fornecedor.text
        fornecedor = next((f for f in self.fornecedores if f["nome"] == nome_escolhido), None)
        if not fornecedor:
            mostrar_mensagem("Selecione o fornecedor onde você comprou")
            return
        try:
            valor = float(self.ids.campo_valor_compra.text.replace(",", "."))
        except ValueError:
            mostrar_mensagem("Digite o valor da nota fiscal")
            return
        if not self.caminho_foto:
            mostrar_mensagem("Tire uma foto da nota fiscal antes de enviar")
            return

        self.ids.botao_enviar_comprovante.disabled = True
        self.ids.botao_enviar_comprovante.text = "Enviando..."
        solicitacao_id = self.solicitacao["id"]

        def sucesso(_):
            self.ids.botao_enviar_comprovante.disabled = False
            self.ids.botao_enviar_comprovante.text = "Enviar comprovante"
            mostrar_mensagem("Comprovante enviado! A conta a pagar já foi gerada.")
            self.manager.current = "estoque_tecnico"

        def erro(e):
            self.ids.botao_enviar_comprovante.disabled = False
            self.ids.botao_enviar_comprovante.text = "Enviar comprovante"
            if isinstance(e, ErroConexao):
                mostrar_mensagem("Sem internet — o envio do comprovante precisa de conexão.")
            else:
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao enviar comprovante")

        rodar_em_background(
            lambda: app.api.enviar_comprovante_compra(solicitacao_id, fornecedor["id"], valor, self.caminho_foto),
            sucesso, erro,
        )


class TelaAnaliseEta(Screen):
    def on_pre_enter(self):
        for id_campo in [
            "campo_vazao", "campo_turbidez_bruta", "campo_turbidez_filtrada", "campo_turbidez_tratada",
            "campo_ph_bruta", "campo_ph_tratada", "campo_sulfato", "campo_cloro_dosagem",
            "campo_cloro_residual", "campo_cor_bruta", "campo_cor_tratada", "campo_observacoes_analise",
        ]:
            self.ids[id_campo].text = ""
        agora = datetime.datetime.now()
        horarios = [f"{h:02d}:00" for h in range(0, 24, 2)]
        self.ids.spinner_horario_coleta.values = horarios
        # Sugere o horário par mais próximo de agora, só pra facilitar
        self.ids.spinner_horario_coleta.text = min(horarios, key=lambda h: abs(int(h[:2]) - agora.hour))

    def _valor_ou_none(self, texto):
        texto = texto.strip().replace(",", ".")
        return float(texto) if texto else None

    def registrar(self):
        app = MDApp.get_running_app()

        try:
            dados = {
                "vazao_ls": self._valor_ou_none(self.ids.campo_vazao.text),
                "turbidez_bruta": self._valor_ou_none(self.ids.campo_turbidez_bruta.text),
                "turbidez_filtrada": self._valor_ou_none(self.ids.campo_turbidez_filtrada.text),
                "turbidez_tratada": self._valor_ou_none(self.ids.campo_turbidez_tratada.text),
                "ph_bruta": self._valor_ou_none(self.ids.campo_ph_bruta.text),
                "ph_tratada": self._valor_ou_none(self.ids.campo_ph_tratada.text),
                "sulfato_dosagem": self._valor_ou_none(self.ids.campo_sulfato.text),
                "cloro_dosagem": self._valor_ou_none(self.ids.campo_cloro_dosagem.text),
                "cloro_residual": self._valor_ou_none(self.ids.campo_cloro_residual.text),
                "cor_bruta": self._valor_ou_none(self.ids.campo_cor_bruta.text),
                "cor_tratada": self._valor_ou_none(self.ids.campo_cor_tratada.text),
            }
        except ValueError:
            mostrar_mensagem("Confira os valores — só números (use ponto ou vírgula pra decimal)")
            return

        if all(v is None for v in dados.values()):
            mostrar_mensagem("Preencha ao menos um parâmetro")
            return

        hora_escolhida = self.ids.spinner_horario_coleta.text
        hoje = datetime.date.today()
        h, m = [int(x) for x in hora_escolhida.split(":")]
        coletado_em = datetime.datetime(hoje.year, hoje.month, hoje.day, h, m)

        dados["coletado_em"] = coletado_em.isoformat()
        dados["observacoes"] = self.ids.campo_observacoes_analise.text.strip() or None

        self.ids.botao_registrar_analise.disabled = True
        self.ids.botao_registrar_analise.text = "Registrando..."

        def sucesso(resultado):
            self.ids.botao_registrar_analise.disabled = False
            self.ids.botao_registrar_analise.text = "Registrar análise"
            if resultado.get("conforme") is False:
                alertas = json.loads(resultado["alertas"]) if resultado.get("alertas") else []
                mensagem = "⚠ Análise registrada, mas fora do padrão:\n" + "\n".join(alertas)
                mostrar_mensagem(mensagem, titulo="Atenção — fora da Portaria 888/2021")
            else:
                mostrar_mensagem("Análise registrada — todos os parâmetros dentro do padrão!")
            self.manager.current = "estoque_tecnico"

        def erro(e):
            self.ids.botao_registrar_analise.disabled = False
            self.ids.botao_registrar_analise.text = "Registrar análise"
            if isinstance(e, ErroConexao):
                mostrar_mensagem("Sem internet — o registro de análise precisa de conexão.")
            else:
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao registrar análise")

        rodar_em_background(lambda: app.api.registrar_analise_eta(dados), sucesso, erro)


class TelaLavagemFiltro(Screen):
    def on_pre_enter(self):
        agora = datetime.datetime.now()
        self.ids.campo_hora_lavagem.text = agora.strftime("%H:%M")
        self.ids.campo_tempo_lavagem.text = ""
        self.ids.campo_volume_lavagem.text = ""

    def registrar(self):
        app = MDApp.get_running_app()
        try:
            h, m = [int(x) for x in self.ids.campo_hora_lavagem.text.strip().split(":")]
            tempo = float(self.ids.campo_tempo_lavagem.text.replace(",", ".")) if self.ids.campo_tempo_lavagem.text.strip() else None
            volume = float(self.ids.campo_volume_lavagem.text.replace(",", ".")) if self.ids.campo_volume_lavagem.text.strip() else None
        except ValueError:
            mostrar_mensagem("Confira a hora (HH:MM) e os valores numéricos")
            return

        hoje = datetime.date.today()
        hora_completa = datetime.datetime(hoje.year, hoje.month, hoje.day, h, m)

        self.ids.botao_registrar_lavagem.disabled = True
        self.ids.botao_registrar_lavagem.text = "Registrando..."

        def sucesso(_):
            self.ids.botao_registrar_lavagem.disabled = False
            self.ids.botao_registrar_lavagem.text = "Registrar"
            mostrar_mensagem("Lavagem do filtro registrada!")
            self.manager.current = "estoque_tecnico"

        def erro(e):
            self.ids.botao_registrar_lavagem.disabled = False
            self.ids.botao_registrar_lavagem.text = "Registrar"
            if isinstance(e, ErroConexao):
                mostrar_mensagem("Sem internet — o registro precisa de conexão.")
            else:
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao registrar lavagem")

        rodar_em_background(
            lambda: app.api.registrar_lavagem_filtro(hora_completa.isoformat(), tempo, volume), sucesso, erro
        )


class TelaLista(Screen):
    def on_pre_enter(self):
        self.carregar()

    def carregar(self):
        app = MDApp.get_running_app()
        lista_widget = self.ids.lista_chamados
        lista_widget.clear_widgets()
        lista_widget.add_widget(OneLineListItem(text="Carregando..."))
        self.ids.aviso_offline.text = ""

        def sucesso(chamados):
            # Online: salva no cache local e tenta sincronizar pendências
            db_local.salvar_cache_chamados(app.user_data_dir, chamados)
            sincronizados, restando = sincronizador.sincronizar(app.user_data_dir, app.api)
            if sincronizados:
                mostrar_mensagem(f"{sincronizados} ação(ões) pendente(s) sincronizada(s)!")
                chamados = db_local.carregar_cache_chamados(app.user_data_dir)
            self._exibir(chamados, restando)

        def erro(e):
            # Offline: mostra o que tiver salvo localmente
            chamados_cache = db_local.carregar_cache_chamados(app.user_data_dir)
            pendentes = db_local.contar_pendentes(app.user_data_dir)
            if isinstance(e, ErroConexao):
                self.ids.aviso_offline.text = (
                    f"🔌 Sem internet — mostrando dados salvos"
                    + (f" ({pendentes} ação(ões) aguardando sincronizar)" if pendentes else "")
                )
                self._exibir(chamados_cache, pendentes)
            else:
                mostrar_mensagem(str(e))
                self._exibir(chamados_cache, pendentes)

        rodar_em_background(app.api.listar_meus_chamados, sucesso, erro)

    def _exibir(self, chamados, pendentes):
        lista_widget = self.ids.lista_chamados
        lista_widget.clear_widgets()

        pendentes_status = [c for c in chamados if c["status"] in ("atribuido", "em_andamento")]

        if not pendentes_status:
            lista_widget.add_widget(OneLineListItem(text="Nenhum chamado pendente pra você"))
            return

        for chamado in pendentes_status:
            texto_principal = f"#{chamado['id']} — {TIPO_LABEL.get(chamado['tipo'], chamado['tipo'])} ({chamado['prioridade']})"
            texto_secundario = STATUS_LABEL.get(chamado["status"], chamado["status"])
            item = TwoLineListItem(
                text=texto_principal,
                secondary_text=texto_secundario,
                on_release=lambda x, c=chamado: self.abrir_detalhe(c),
            )
            lista_widget.add_widget(item)

    def abrir_detalhe(self, chamado):
        tela_detalhe = self.manager.get_screen("detalhe")
        tela_detalhe.carregar_chamado(chamado)
        self.manager.current = "detalhe"


class TelaDetalhe(Screen):
    chamado = ObjectProperty(None)
    fotos_tiradas = []
    itens_estoque_disponiveis = []
    itens_estoque_selecionados = []
    catalogo_disponivel = []

    def carregar_chamado(self, chamado):
        app = MDApp.get_running_app()
        self.chamado = chamado
        self.fotos_tiradas = []
        self.itens_estoque_selecionados = []
        self.ids.texto_tipo.text = f"Tipo: {TIPO_LABEL.get(chamado['tipo'], chamado['tipo'])}"
        self.ids.texto_prioridade.text = f"Prioridade: {chamado['prioridade']}"
        self.ids.texto_descricao.text = f"Problema relatado: {chamado['descricao_problema']}"
        self.ids.texto_status.text = f"Status: {STATUS_LABEL.get(chamado['status'], chamado['status'])}"

        self.ids.botao_iniciar.disabled = chamado["status"] != "atribuido"
        self.ids.botao_iniciar.text = "INICIAR ATENDIMENTO" if chamado["status"] == "atribuido" else "Atendimento já iniciado"
        self.ids.campo_solucao.text = ""
        self.ids.campo_materiais.text = ""
        self.ids.texto_fotos.text = "Nenhuma foto tirada ainda"
        self.ids.texto_estoque_selecionado.text = "Nenhum item do estoque adicionado"
        self.ids.campo_quantidade_estoque.text = ""
        self.ids.campo_quantidade_solicitar.text = ""

        # Reseta o checklist pra um chamado novo
        for id_checkbox, _ in CHECKLIST_ITENS:
            self.ids[id_checkbox].active = False

        # Busca o estoque do técnico (best-effort — se estiver offline, só
        # não aparece a lista, mas o técnico ainda pode descrever no texto livre)
        def sucesso(itens):
            self.itens_estoque_disponiveis = itens
            nomes = [f"{i['nome_item']} ({i['quantidade']:.0f} {i['unidade_medida']})" for i in itens]
            self.ids.spinner_estoque.values = nomes or ["(sem itens em mãos)"]
            self.ids.spinner_estoque.text = nomes[0] if nomes else "(sem itens em mãos)"

        def erro(e):
            self.ids.spinner_estoque.values = ["(estoque indisponível offline)"]
            self.ids.spinner_estoque.text = "(estoque indisponível offline)"

        rodar_em_background(app.api.meu_estoque, sucesso, erro)

        # Busca o catálogo geral (todos os itens cadastrados), pra poder solicitar
        def sucesso_catalogo(itens):
            self.catalogo_disponivel = itens
            nomes = [i["nome"] for i in itens]
            self.ids.spinner_catalogo.values = nomes or ["(nenhum item cadastrado)"]
            self.ids.spinner_catalogo.text = nomes[0] if nomes else "(nenhum item cadastrado)"

        def erro_catalogo(e):
            self.ids.spinner_catalogo.values = ["(catálogo indisponível offline)"]
            self.ids.spinner_catalogo.text = "(catálogo indisponível offline)"

        rodar_em_background(app.api.catalogo_estoque, sucesso_catalogo, erro_catalogo)

    def _coletar_checklist(self):
        return {label: self.ids[id_checkbox].active for id_checkbox, label in CHECKLIST_ITENS}

    def solicitar_material(self):
        app = MDApp.get_running_app()
        nome_escolhido = self.ids.spinner_catalogo.text
        item = next((i for i in self.catalogo_disponivel if i["nome"] == nome_escolhido), None)
        if not item:
            mostrar_mensagem("Selecione um item válido do catálogo")
            return
        try:
            quantidade = float(self.ids.campo_quantidade_solicitar.text.replace(",", "."))
        except ValueError:
            mostrar_mensagem("Digite uma quantidade válida")
            return
        if quantidade <= 0:
            mostrar_mensagem("Quantidade precisa ser maior que zero")
            return

        chamado_id = self.chamado["id"]
        self.ids.botao_solicitar.disabled = True
        self.ids.botao_solicitar.text = "Enviando..."

        def sucesso(_):
            self.ids.botao_solicitar.disabled = False
            self.ids.botao_solicitar.text = "Solicitar"
            self.ids.campo_quantidade_solicitar.text = ""
            mostrar_mensagem("Solicitação enviada! Aguarde a aprovação do operador.")

        def erro(e):
            self.ids.botao_solicitar.disabled = False
            self.ids.botao_solicitar.text = "Solicitar"
            if isinstance(e, ErroConexao):
                mostrar_mensagem("Sem internet — solicitações precisam de conexão (o operador precisa ver na hora).")
            else:
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao solicitar material")

        rodar_em_background(lambda: app.api.solicitar_material(item["id"], quantidade, chamado_id), sucesso, erro)

    def adicionar_material_estoque(self):
        escolha = self.ids.spinner_estoque.text
        item = next(
            (i for i in self.itens_estoque_disponiveis
             if escolha.startswith(i["nome_item"])),
            None,
        )
        if not item:
            mostrar_mensagem("Selecione um item válido do estoque")
            return
        try:
            quantidade = float(self.ids.campo_quantidade_estoque.text.replace(",", "."))
        except ValueError:
            mostrar_mensagem("Digite uma quantidade válida")
            return
        if quantidade <= 0:
            mostrar_mensagem("Quantidade precisa ser maior que zero")
            return

        self.itens_estoque_selecionados.append({"item_id": item["item_id"], "quantidade": quantidade})
        resumo = ", ".join(
            f"{sel['quantidade']:.0f}x item#{sel['item_id']}" for sel in self.itens_estoque_selecionados
        )
        self.ids.texto_estoque_selecionado.text = f"Itens adicionados: {resumo}"
        self.ids.campo_quantidade_estoque.text = ""
        mostrar_mensagem("Item adicionado à lista de baixa")

    def iniciar(self):
        app = MDApp.get_running_app()
        self.ids.botao_iniciar.disabled = True
        self.ids.botao_iniciar.text = "Iniciando..."
        chamado_id = self.chamado["id"]

        def sucesso(atualizado):
            self.chamado = atualizado
            self.ids.texto_status.text = f"Status: {STATUS_LABEL.get(atualizado['status'], atualizado['status'])}"
            self.ids.botao_iniciar.text = "Atendimento iniciado"
            mostrar_mensagem("Atendimento iniciado")

        def erro(e):
            if isinstance(e, ErroConexao):
                # Sem internet: guarda a ação localmente e segue o atendimento normalmente
                db_local.enfileirar_acao(app.user_data_dir, "iniciar", chamado_id, {})
                db_local.atualizar_status_local(app.user_data_dir, chamado_id, "em_andamento")
                self.chamado["status"] = "em_andamento"
                self.ids.texto_status.text = "Status: Em andamento (offline — será sincronizado)"
                self.ids.botao_iniciar.text = "Atendimento iniciado (offline)"
                mostrar_mensagem("Sem internet — atendimento iniciado localmente, será sincronizado depois.")
            else:
                self.ids.botao_iniciar.disabled = False
                self.ids.botao_iniciar.text = "INICIAR ATENDIMENTO"
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao iniciar atendimento")

        rodar_em_background(lambda: app.api.iniciar_atendimento(chamado_id), sucesso, erro)

    def tirar_foto(self):
        """
        No celular (Android): abre a câmera nativa de verdade via plyer.
        No PC (fora do Android): não existe câmera nativa acessível assim,
        então abre um seletor de arquivo pra escolher uma foto já existente
        no computador — só pra dar pra testar o fluxo de fechamento sem
        precisar de um celular em mãos.
        """
        from plyer import camera

        app = MDApp.get_running_app()
        pasta = app.user_data_dir
        nome_arquivo = f"chamado_{self.chamado['id']}_{len(self.fotos_tiradas)}.jpg"
        caminho = os.path.join(pasta, nome_arquivo)

        def ao_terminar(caminho_salvo):
            self.fotos_tiradas.append(caminho_salvo)
            self.ids.texto_fotos.text = f"{len(self.fotos_tiradas)} foto(s) tirada(s)"
            mostrar_mensagem("Foto adicionada")

        try:
            camera.take_picture(filename=caminho, on_complete=lambda path: ao_terminar(caminho))
        except NotImplementedError:
            self._escolher_foto_do_pc(ao_terminar)

    def _escolher_foto_do_pc(self, ao_terminar):
        """Modo de teste no PC: escolhe uma imagem já existente no computador."""
        from plyer import filechooser

        def ao_selecionar(selecao):
            if selecao:
                ao_terminar(selecao[0])
            else:
                mostrar_mensagem("Nenhuma foto selecionada")

        try:
            filechooser.open_file(
                title="Escolha uma foto (modo teste no PC)",
                filters=[("Imagens", "*.jpg", "*.jpeg", "*.png")],
                on_selection=ao_selecionar,
            )
        except Exception:
            mostrar_mensagem("Não foi possível abrir o seletor de arquivos")

    def fechar_chamado(self):
        app = MDApp.get_running_app()
        descricao = self.ids.campo_solucao.text.strip()
        materiais = self.ids.campo_materiais.text.strip()

        if not descricao:
            mostrar_mensagem("Descreva o que foi feito antes de fechar")
            return
        if not self.fotos_tiradas:
            mostrar_mensagem("Tire ao menos 1 foto antes de fechar")
            return

        checklist = self._coletar_checklist()
        chamado_id = self.chamado["id"]
        fotos = list(self.fotos_tiradas)
        itens_estoque = list(self.itens_estoque_selecionados)

        self.ids.botao_fechar.disabled = True
        self.ids.botao_fechar.text = "Enviando..."

        def sucesso(_):
            self.ids.botao_fechar.disabled = False
            self.ids.botao_fechar.text = "Fechar chamado"
            mostrar_mensagem("Chamado fechado com sucesso!")
            self.manager.current = "lista"
            Clock.schedule_once(lambda dt: self.manager.get_screen("lista").carregar(), 0.3)

        def erro(e):
            if isinstance(e, ErroConexao):
                # Sem internet: guarda tudo (descrição, checklist, materiais e
                # os caminhos das fotos já tiradas) pra enviar depois.
                db_local.enfileirar_acao(app.user_data_dir, "fechar", chamado_id, {
                    "descricao_solucao": descricao,
                    "checklist": checklist,
                    "materiais_utilizados": materiais,
                    "fotos": fotos,
                    "itens_estoque_usados": itens_estoque,
                })
                db_local.atualizar_status_local(app.user_data_dir, chamado_id, "concluido")
                self.ids.botao_fechar.disabled = False
                self.ids.botao_fechar.text = "Fechar chamado"
                mostrar_mensagem("Sem internet — chamado fechado localmente, será enviado quando houver sinal.")
                self.manager.current = "lista"
                Clock.schedule_once(lambda dt: self.manager.get_screen("lista").carregar(), 0.3)
            else:
                self.ids.botao_fechar.disabled = False
                self.ids.botao_fechar.text = "Fechar chamado"
                mostrar_mensagem(str(e) if isinstance(e, ApiError) else "Falha ao fechar chamado")

        rodar_em_background(
            lambda: app.api.fechar_chamado(
                chamado_id, descricao, fotos, checklist=checklist, materiais=materiais,
                itens_estoque_usados=itens_estoque,
            ),
            sucesso, erro,
        )


class TecnicoApp(AppSiga):
    title = "SIGA · Técnico"
    api = None
    novidades_texto = StringProperty("")
    chamados_card_texto = StringProperty("Atendimentos atribuídos a você")
    _relogio_vivo = None

    # --- ao vivo: a cada 15 s olha se chegou chamado novo ou resposta de solicitação (só leitura; offline = silêncio) ---
    def iniciar_ao_vivo(self):
        self.parar_ao_vivo()
        self.vivo = vivo.EstadoTecnico()
        self.novidades_texto = ""
        self.chamados_card_texto = "Atendimentos atribuídos a você"
        self._relogio_vivo = Clock.schedule_interval(lambda dt: self._consultar_vivo(), vivo.INTERVALO_S)
        self._consultar_vivo()

    def parar_ao_vivo(self):
        if self._relogio_vivo:
            self._relogio_vivo.cancel()
            self._relogio_vivo = None
        self.novidades_texto = ""
        self.chamados_card_texto = "Atendimentos atribuídos a você"

    def _consultar_vivo(self):
        api = self.api
        if api is None or self._relogio_vivo is None or not api.token:
            return

        def buscar():
            chamados = api.listar_meus_chamados()
            try:
                solicitacoes = api.minhas_solicitacoes()
            except Exception:
                solicitacoes = None
            return chamados, solicitacoes

        def sucesso(res):
            if self.api is not api or self._relogio_vivo is None or not api.token:  # saiu enquanto a resposta vinha
                return
            mudancas = self.vivo.receber(*res)
            self.chamados_card_texto = self.vivo.texto_cartao_chamados()
            if mudancas["chamados_novos"]:
                self.novidades_texto = f"{len(mudancas['chamados_novos'])} chamado(s) novo(s) para você!"
            elif not self.vivo.abertos:
                self.novidades_texto = ""
            if mudancas["avisos"]:
                avisar_novidade("\n\n".join(mudancas["avisos"]),
                                "Chamado novo" if mudancas["chamados_novos"] else "Solicitação respondida")
            atual = self.root.current
            if mudancas["chamados_novos"] and atual == "lista":
                self.root.get_screen("lista").carregar()
            if mudancas["solicitacoes"] and atual == "minhas_solicitacoes":
                self.root.get_screen("minhas_solicitacoes").carregar()

        rodar_em_background(buscar, sucesso, lambda e: None)

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
        self.nome_app = "App do técnico"
        with open(os.path.join(self.pasta_app, "telas_tecnico.kv"), encoding="utf-8") as f:
            raiz = self.carregar_base(f.read())
        raiz.current = "splash"
        return raiz


if __name__ == "__main__":
    TecnicoApp().run()
