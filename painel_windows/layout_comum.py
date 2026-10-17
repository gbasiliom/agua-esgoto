"""Peças de layout compartilhadas pelo painel do administrador (main.py) e pelo painel do
químico (main_quimico.py): barra superior com logo, rodapé, splash e tela de login no estilo
do app Acordes de Davi (barra de cima + cartão central com faixa de título + rodapé fino)."""
import os
import sys
import customtkinter as ctk
from tkinter import messagebox
from PIL import Image as ImagemPIL

import tema
from api_client import ApiError
from async_helper import rodar_em_background

if getattr(sys, "frozen", False):
    _BASE = sys._MEIPASS
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_ASSETS = os.path.join(_BASE, "assets")

TEXTO_RODAPE = "SAAE de Chalé • SIGA — Sistema Integrado de Gestão de Água e Esgoto"


def carregar_logo(largura):
    """Logo oficial do SAAE (assets/logo_saae.png, PNG transparente). CTkImage ou None."""
    caminho = os.path.join(PASTA_ASSETS, "logo_saae.png")
    if not os.path.exists(caminho):
        return None
    try:
        img = ImagemPIL.open(caminho).convert("RGBA")
        altura = int(largura * img.height / img.width)
        return ctk.CTkImage(light_image=img, dark_image=img, size=(largura, altura))
    except Exception:
        return None


def _brasao(master, altura):
    caminho = os.path.join(PASTA_ASSETS, "brasao.png")  # fornecido pela Prefeitura/SAAE; opcional
    if not os.path.exists(caminho):
        return None
    try:
        img = ImagemPIL.open(caminho)
        imagem = ctk.CTkImage(light_image=img, dark_image=img, size=(int(altura * img.width / img.height), altura))
        return ctk.CTkLabel(master, image=imagem, text="")
    except Exception:
        return None


def barra_superior(master, titulo="SIGA", subtitulo="Sistema Integrado de Gestão de Água e Esgoto", compacta=False):
    """Barra azul-marinho: logo (num chip branco) + título à esquerda; `barra.menu` à direita."""
    barra = ctk.CTkFrame(master, fg_color=tema.AZUL, corner_radius=0)
    logo = carregar_logo(86 if compacta else 120)
    if logo is not None:  # a logo é azul: sobre o fundo marinho ela some, então vai num chip branco
        chip = ctk.CTkFrame(barra, fg_color="white", corner_radius=8)
        chip.pack(side="left", padx=(18, 0), pady=7 if compacta else 10)
        ctk.CTkLabel(chip, image=logo, text="").pack(padx=7, pady=3)
    brasao = None if compacta else _brasao(barra, 46)
    if brasao is not None:
        brasao.pack(side="left", padx=(12, 0), pady=10)
    if not compacta or titulo or subtitulo:
        bloco = ctk.CTkFrame(barra, fg_color="transparent")
        bloco.pack(side="left", padx=(14, 10), pady=10)
        ctk.CTkLabel(bloco, text=titulo, font=ctk.CTkFont(size=17, weight="bold"), text_color="white").pack(anchor="w")
        ctk.CTkLabel(bloco, text=subtitulo, font=ctk.CTkFont(size=11), text_color="#BCD0F0").pack(anchor="w")
    barra.menu = ctk.CTkFrame(barra, fg_color="transparent", height=1)
    barra.menu.pack(side="right", padx=16, pady=4 if compacta else 0)
    return barra


def pilula(master, texto, comando, ativa=False, tamanho=13):
    """Botão em pílula do menu superior (ativa = mais escura)."""
    return ctk.CTkButton(
        master, text=texto, width=10, height=32, corner_radius=8,
        fg_color=tema.AZUL_ESCURO if ativa else "transparent", hover_color=tema.AZUL_HOVER,
        text_color="white", font=ctk.CTkFont(size=tamanho), command=comando,
    )


def rodape(master):
    r = ctk.CTkFrame(master, fg_color=tema.BRANCO, corner_radius=0)
    ctk.CTkLabel(r, text=TEXTO_RODAPE, font=ctk.CTkFont(size=10), text_color=tema.TEXTO_SUAVE).pack(pady=6)
    return r


class TelaSplash(ctk.CTkFrame):
    """Abertura: fundo azul-marinho, logo no cartão branco e botão "Pular ›" (como a intro do Acordes de Davi)."""

    def __init__(self, master, ao_terminar, duracao_ms=6000, titulo="SIGA",
                 subtitulo="Sistema Integrado de Gestão de Água e Esgoto", prefixo="Projeto "):
        super().__init__(master, fg_color=tema.AZUL, corner_radius=0)
        self._ao_terminar = ao_terminar
        self._feito = False

        ctk.CTkButton(
            self, text="Pular  ›", width=90, height=32, corner_radius=16, fg_color=tema.AZUL_HOVER,
            hover_color=tema.DESTAQUE, text_color="white", command=self.terminar,
        ).place(relx=1.0, x=-24, y=20, anchor="ne")

        centro = ctk.CTkFrame(self, fg_color=tema.AZUL, corner_radius=0)
        centro.place(relx=0.5, rely=0.46, anchor="center")
        cartao = ctk.CTkFrame(centro, fg_color="white", corner_radius=18)
        cartao.pack()
        logo = carregar_logo(380)
        if logo is not None:
            ctk.CTkLabel(cartao, image=logo, text="").pack(padx=36, pady=28)
        else:
            ctk.CTkLabel(cartao, text="SAAE Chalé", font=ctk.CTkFont(size=40, weight="bold"),
                         text_color=tema.AZUL).pack(padx=60, pady=40)
        titulo_f = ctk.CTkFrame(centro, fg_color=tema.AZUL, corner_radius=0)
        titulo_f.pack(pady=(26, 0))
        ctk.CTkLabel(titulo_f, text=prefixo, font=ctk.CTkFont(size=26, weight="bold"),
                     text_color="white").pack(side="left")
        ctk.CTkLabel(titulo_f, text=titulo, font=ctk.CTkFont(size=26, weight="bold"),
                     text_color="#7FB2F0").pack(side="left")
        ctk.CTkLabel(centro, text=subtitulo, font=ctk.CTkFont(size=13), text_color="#BCD0F0").pack(pady=(6, 0))
        self.after(duracao_ms, self.terminar)

    def terminar(self):
        if self._feito:
            return
        self._feito = True
        self._ao_terminar()


class CartaoLogin(ctk.CTkFrame):
    """Cartão de login (faixa azul com logo + título, aviso, campos, botão). Valida o tipo de usuário."""

    def __init__(self, master, api, ao_logar, titulo_cartao, subtitulo_cartao, aviso, tipos_aceitos, msg_negado):
        super().__init__(master, fg_color="white", corner_radius=16, border_width=1, border_color=tema.LINHA)
        self.api, self.ao_logar = api, ao_logar
        self.tipos_aceitos, self.msg_negado = tuple(tipos_aceitos), msg_negado

        faixa = ctk.CTkFrame(self, fg_color=tema.AZUL, corner_radius=16)
        faixa.pack(fill="x")
        ctk.CTkFrame(faixa, fg_color=tema.AZUL, corner_radius=0, height=18).pack(side="bottom", fill="x")
        logo = carregar_logo(150)
        if logo is not None:
            chip = ctk.CTkFrame(faixa, fg_color="white", corner_radius=8)
            chip.pack(pady=(22, 8))
            ctk.CTkLabel(chip, image=logo, text="").pack(padx=10, pady=5)
        ctk.CTkLabel(faixa, text=titulo_cartao, font=ctk.CTkFont(size=19, weight="bold"),
                     text_color="white").pack(padx=60)
        ctk.CTkLabel(faixa, text=subtitulo_cartao, font=ctk.CTkFont(size=12), text_color="#BCD0F0").pack(pady=(2, 6))

        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(fill="x", padx=30, pady=(14, 26))
        ctk.CTkLabel(corpo, text="🔒  " + aviso, font=ctk.CTkFont(size=11), text_color=tema.TEXTO_SUAVE,
                     anchor="w", wraplength=320, justify="left").pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(corpo, text="E-MAIL OU TELEFONE", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x")
        self.campo_usuario = ctk.CTkEntry(corpo, width=320, height=38, border_color=tema.LINHA,
                                          fg_color="white", text_color=tema.TEXTO)
        self.campo_usuario.pack(fill="x", pady=(2, 12))
        ctk.CTkLabel(corpo, text="SENHA", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x")
        self.campo_senha = ctk.CTkEntry(corpo, width=320, height=38, show="•", border_color=tema.LINHA,
                                        fg_color="white", text_color=tema.TEXTO)
        self.campo_senha.pack(fill="x", pady=(2, 16))
        self.campo_senha.bind("<Return>", lambda _e: self.entrar())
        self.campo_usuario.bind("<Return>", lambda _e: self.campo_senha.focus())

        self.botao_entrar = ctk.CTkButton(corpo, text="Entrar no Painel", height=40, fg_color=tema.AZUL,
                                          hover_color=tema.AZUL_HOVER, font=ctk.CTkFont(size=14, weight="bold"),
                                          command=self.entrar)
        self.botao_entrar.pack(fill="x")
        ctk.CTkButton(corpo, text="Esqueci minha senha", height=30, fg_color="transparent", text_color=tema.DESTAQUE,
                      hover_color=tema.AZUL_CLARO, font=ctk.CTkFont(size=12), command=self.esqueci_senha
                      ).pack(fill="x", pady=(8, 0))

    def esqueci_senha(self):
        from seguranca_painel import JanelaEsqueciSenha
        JanelaEsqueciSenha(self.winfo_toplevel(), self.api, self.campo_usuario.get().strip())

    def entrar(self):
        usuario = self.campo_usuario.get().strip()
        senha = self.campo_senha.get()
        if not usuario or not senha:
            messagebox.showwarning("Atenção", "Informe e-mail/telefone e a senha.")
            return
        self.botao_entrar.configure(state="disabled", text="Entrando...")

        def sucesso(dados):
            self.botao_entrar.configure(state="normal", text="Entrar no Painel")
            if dados.get("requer_2fa"):
                from seguranca_painel import JanelaCodigo2FA
                JanelaCodigo2FA(self.winfo_toplevel(), self.api, self._depois_do_login, self._desistiu)
                return
            self._depois_do_login()

        def erro(e):
            self.botao_entrar.configure(state="normal", text="Entrar no Painel")
            if isinstance(e, ApiError):
                messagebox.showerror("Erro no login", str(e))
            else:
                messagebox.showerror("Erro", "Não foi possível conectar à API. Verifique o endereço configurado.")

        rodar_em_background(self, lambda: self.api.login(usuario, senha), sucesso, erro)

    def _depois_do_login(self):
        if self.api.tipo_usuario not in self.tipos_aceitos:
            rodar_em_background(self, self.api.sair)  # encerra no servidor a sessão que acabou de abrir
            messagebox.showerror("Acesso negado", self.msg_negado)
            return
        if self.api.trocar_senha_pendente:
            from seguranca_painel import JanelaTrocarSenha
            JanelaTrocarSenha(self.winfo_toplevel(), self.api, obrigatoria=True,
                              ao_concluir=self._concluir, ao_cancelar=self._desistiu)
            return
        self._concluir()

    def _desistiu(self):
        rodar_em_background(self, self.api.sair)

    def _concluir(self):
        self.campo_senha.delete(0, "end")
        self.ao_logar()


class TelaLoginBase(ctk.CTkFrame):
    """Login em tela cheia no estilo Acordes de Davi: barra superior + cartão central + rodapé."""

    def __init__(self, master, api, ao_logar, titulo_cartao, subtitulo_cartao, aviso, tipos_aceitos, msg_negado,
                 titulo_barra="SIGA", subtitulo_barra="Sistema Integrado de Gestão de Água e Esgoto"):
        super().__init__(master, fg_color=tema.FUNDO, corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        barra_superior(self, titulo_barra, subtitulo_barra).grid(row=0, column=0, sticky="ew")
        meio = ctk.CTkFrame(self, fg_color="transparent")
        meio.grid(row=1, column=0, sticky="nsew")
        rodape(self).grid(row=2, column=0, sticky="ew")
        self.cartao = CartaoLogin(meio, api, ao_logar, titulo_cartao, subtitulo_cartao, aviso, tipos_aceitos,
                                  msg_negado)
        self.cartao.place(relx=0.5, rely=0.5, anchor="center")
        self.campo_usuario, self.campo_senha = self.cartao.campo_usuario, self.cartao.campo_senha
        self.campo_usuario.focus()

    def entrar(self):
        self.cartao.entrar()


class JanelaLogin(ctk.CTkToplevel):
    """Janela de login (modal) pedida por uma área restrita. Usa um ApiClient PRÓPRIO, então não
    mexe na sessão de quem já está logado. Chama ao_sucesso(api) ou ao_cancelar()."""

    def __init__(self, master, api, titulo, subtitulo, aviso, tipos_aceitos, msg_negado, ao_sucesso, ao_cancelar):
        super().__init__(master, fg_color=tema.FUNDO)
        self.title(titulo)
        self.resizable(False, False)
        self._ao_sucesso, self._ao_cancelar = ao_sucesso, ao_cancelar
        self._concluida = False
        self.protocol("WM_DELETE_WINDOW", self.cancelar)

        quadro = ctk.CTkFrame(self, fg_color="transparent")
        quadro.pack(padx=24, pady=(24, 10))
        self.cartao = CartaoLogin(quadro, api, lambda: self._sucesso(api), titulo, subtitulo, aviso,
                                  tipos_aceitos, msg_negado)
        self.cartao.pack()
        ctk.CTkButton(self, text="Cancelar", height=34, fg_color="white", text_color=tema.TEXTO,
                      border_width=1, border_color=tema.LINHA, hover_color=tema.AZUL_CLARO,
                      command=self.cancelar).pack(fill="x", padx=24, pady=(0, 20))

        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        x = master.winfo_rootx() + max(0, (master.winfo_width() - w) // 2)
        y = master.winfo_rooty() + max(0, (master.winfo_height() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.transient(master)
        self.after(150, self._focar)

    def _focar(self):
        if self.winfo_exists():
            self.grab_set()
            self.cartao.campo_usuario.focus()

    def _sucesso(self, api):
        self._concluida = True
        self.destroy()
        self._ao_sucesso(api)

    def cancelar(self):
        if not self._concluida:
            self._concluida = True
            self.destroy()
            self._ao_cancelar()
