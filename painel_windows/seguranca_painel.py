"""Segurança no painel Windows: janelas de código por e-mail (2FA do admin), "esqueci minha senha",
troca de senha (obrigatória no primeiro acesso), e as telas de Acessos (resetar senha) e Auditoria.

Fica separado de main.py para os dois painéis (Administrador e Químico) usarem as mesmas janelas.
"""
import re
from datetime import datetime, timezone
from tkinter import messagebox

import customtkinter as ctk

import tema
from api_client import ApiError
from async_helper import rodar_em_background

LOCALIDADE_LABEL = {"sede": "Chalé (sede)", "penha_do_coco": "Penha do Coco", "bananal": "Bananal", "agua_limpa": "Água Limpa"}
TIPO_USUARIO_LABEL = {
    "admin": "Administrador", "operador": "Operador", "tecnico": "Técnico", "quimico": "Químico",
    "operador_eta": "Operador de ETA", "cliente": "Morador (cliente)",
}
DICA_SENHA = "Mínimo de 8 caracteres, com pelo menos uma letra e um número. Evite seu nome, e-mail ou telefone."


# --------------------------------------------------------------------------------------
# Peças pequenas
# --------------------------------------------------------------------------------------
def _rotulo(master, texto):
    ctk.CTkLabel(master, text=texto.upper(), font=ctk.CTkFont(size=10, weight="bold"),
                 text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", pady=(8, 0))


def _campo(master, senha=False, largura=340):
    e = ctk.CTkEntry(master, width=largura, height=38, border_color=tema.LINHA, fg_color="white",
                     text_color=tema.TEXTO, show="•" if senha else "")
    e.pack(fill="x", pady=(2, 0))
    return e


def _botao(master, texto, comando, principal=True, **kw):
    if principal:
        return ctk.CTkButton(master, text=texto, height=40, fg_color=tema.AZUL, hover_color=tema.AZUL_HOVER,
                             font=ctk.CTkFont(size=14, weight="bold"), command=comando, **kw)
    return ctk.CTkButton(master, text=texto, height=36, fg_color="white", text_color=tema.TEXTO, border_width=1,
                         border_color=tema.LINHA, hover_color=tema.AZUL_CLARO, command=comando, **kw)


def _msg(label, texto, ok=False):
    label.configure(text=texto, text_color=tema.OK if ok else tema.ERRO)


def problemas_senha(nova, repetir=None):
    """Confere antes de ir ao servidor (o servidor confere de novo). Texto pronto ou ''."""
    if repetir is not None and nova != repetir:
        return "As duas senhas não são iguais."
    faltas = []
    if len(nova or "") < 8:
        faltas.append("pelo menos 8 caracteres")
    if not re.search(r"[A-Za-zÀ-ÿ]", nova or ""):
        faltas.append("pelo menos uma letra")
    if not re.search(r"\d", nova or ""):
        faltas.append("pelo menos um número")
    return ("A senha precisa ter " + ", ".join(faltas) + ".") if faltas else ""


class _JanelaModal(ctk.CTkToplevel):
    """Janela pequena e centralizada sobre a janela que a abriu."""

    def __init__(self, master, titulo, largura=420):
        super().__init__(master, fg_color=tema.FUNDO)
        self.title(titulo)
        self.resizable(False, False)
        self._largura = largura
        self.corpo = ctk.CTkFrame(self, fg_color="white", corner_radius=14, border_width=1, border_color=tema.LINHA)
        self.corpo.pack(fill="both", expand=True, padx=18, pady=18)
        self.interno = ctk.CTkFrame(self.corpo, fg_color="transparent")
        self.interno.pack(fill="both", expand=True, padx=22, pady=18)
        self._master = master

    def mostrar(self):
        self.update_idletasks()
        w, h = max(self._largura, self.winfo_reqwidth()), self.winfo_reqheight()
        m = self._master
        x = m.winfo_rootx() + max(0, (m.winfo_width() - w) // 2)
        y = m.winfo_rooty() + max(0, (m.winfo_height() - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.after(150, self._focar)

    def _focar(self):
        try:
            if self.winfo_exists():
                self.grab_set()
        except Exception:
            pass


# --------------------------------------------------------------------------------------
# Código por e-mail do administrador (2FA)
# --------------------------------------------------------------------------------------
class JanelaCodigo2FA(_JanelaModal):
    """Depois da senha certa, o admin digita o código de 6 dígitos que chegou no e-mail dele."""

    def __init__(self, master, api, ao_sucesso, ao_cancelar):
        super().__init__(master, "Verificação em duas etapas")
        self.api, self._ao_sucesso, self._ao_cancelar = api, ao_sucesso, ao_cancelar
        self._concluida = False
        self.protocol("WM_DELETE_WINDOW", self.cancelar)
        i = self.interno
        ctk.CTkLabel(i, text="Código de verificação", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x")
        destino = api.email_mascarado or "o e-mail do seu cadastro"
        ctk.CTkLabel(i, text=f"Enviamos um código de 6 dígitos para {destino}. Ele vale por 10 minutos. "
                             "Olhe também a caixa de spam.", font=ctk.CTkFont(size=12), text_color=tema.TEXTO_SUAVE,
                     anchor="w", justify="left", wraplength=340).pack(fill="x", pady=(4, 6))
        _rotulo(i, "Código")
        self.campo = _campo(i)
        self.campo.bind("<Return>", lambda _e: self.confirmar())
        self.aviso = ctk.CTkLabel(i, text="", font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=340)
        self.aviso.pack(fill="x", pady=(6, 0))
        self.botao = _botao(i, "Confirmar", self.confirmar)
        self.botao.pack(fill="x", pady=(10, 6))
        _botao(i, "Cancelar", self.cancelar, principal=False).pack(fill="x")
        self.mostrar()
        self.after(200, self.campo.focus)

    def confirmar(self):
        codigo = self.campo.get().strip()
        if len(re.sub(r"\D", "", codigo)) != 6:
            _msg(self.aviso, "Digite os 6 números do código.")
            return
        self.botao.configure(state="disabled", text="Verificando...")

        def sucesso(_):
            self._concluida = True
            self.destroy()
            self._ao_sucesso()

        def erro(e):
            self.botao.configure(state="normal", text="Confirmar")
            _msg(self.aviso, str(e) if isinstance(e, ApiError) else "Não foi possível conectar à API.")

        rodar_em_background(self, lambda: self.api.verificar_2fa(codigo), sucesso, erro)

    def cancelar(self):
        if not self._concluida:
            self._concluida = True
            self.destroy()
            self._ao_cancelar()


# --------------------------------------------------------------------------------------
# Esqueci minha senha
# --------------------------------------------------------------------------------------
class JanelaEsqueciSenha(_JanelaModal):
    """Passo 1: e-mail/telefone -> código por e-mail. Passo 2: código + nova senha."""

    def __init__(self, master, api, identificador=""):
        super().__init__(master, "Recuperar senha")
        self.api = api
        self._ident = ""
        i = self.interno
        ctk.CTkLabel(i, text="Recuperar senha", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x")
        ctk.CTkLabel(i, text="Informe o e-mail ou o telefone do seu cadastro. Enviaremos um código de 6 dígitos "
                             "para o e-mail da conta.", font=ctk.CTkFont(size=12), text_color=tema.TEXTO_SUAVE,
                     anchor="w", justify="left", wraplength=340).pack(fill="x", pady=(4, 6))
        _rotulo(i, "E-mail ou telefone")
        self.campo_ident = _campo(i)
        if identificador:
            self.campo_ident.insert(0, identificador)
        self.campo_ident.bind("<Return>", lambda _e: self.enviar())
        self.botao_enviar = _botao(i, "Enviar código", self.enviar)
        self.botao_enviar.pack(fill="x", pady=(12, 0))

        self.etapa2 = ctk.CTkFrame(i, fg_color="transparent")
        _rotulo(self.etapa2, "Código recebido por e-mail")
        self.campo_codigo = _campo(self.etapa2)
        _rotulo(self.etapa2, "Nova senha")
        self.campo_nova = _campo(self.etapa2, senha=True)
        _rotulo(self.etapa2, "Repita a nova senha")
        self.campo_nova2 = _campo(self.etapa2, senha=True)
        self.campo_nova2.bind("<Return>", lambda _e: self.redefinir())
        ctk.CTkLabel(self.etapa2, text=DICA_SENHA, font=ctk.CTkFont(size=10), text_color=tema.TEXTO_SUAVE,
                     anchor="w", justify="left", wraplength=340).pack(fill="x", pady=(4, 0))
        self.botao_redefinir = _botao(self.etapa2, "Redefinir senha", self.redefinir)
        self.botao_redefinir.pack(fill="x", pady=(10, 0))

        self.aviso = ctk.CTkLabel(i, text="", font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=340)
        self.aviso.pack(fill="x", pady=(8, 0))
        _botao(i, "Fechar", self.destroy, principal=False).pack(fill="x", pady=(6, 0))
        self.mostrar()
        self.after(200, self.campo_ident.focus)

    def enviar(self):
        ident = self.campo_ident.get().strip()
        if not ident:
            _msg(self.aviso, "Informe o e-mail ou o telefone do seu cadastro.")
            return
        self.botao_enviar.configure(state="disabled", text="Enviando...")
        _msg(self.aviso, "Enviando...", ok=True)

        def sucesso(_texto):
            self._ident = ident
            self.botao_enviar.configure(state="normal", text="Enviar de novo")
            self.etapa2.pack(fill="x", after=self.botao_enviar)
            _msg(self.aviso, "Se existir cadastro com esse e-mail ou telefone, o código foi enviado ao e-mail da conta. "
                             "Digite-o abaixo. Olhe também a caixa de spam.", ok=True)
            self.update_idletasks()
            self.geometry(f"{max(self._largura, self.winfo_reqwidth())}x{self.winfo_reqheight()}")
            self.campo_codigo.focus()

        def erro(e):
            self.botao_enviar.configure(state="normal", text="Enviar código")
            _msg(self.aviso, str(e) if isinstance(e, ApiError) else "Não foi possível conectar à API.")

        rodar_em_background(self, lambda: self.api.esqueci_senha(ident), sucesso, erro)

    def redefinir(self):
        codigo = self.campo_codigo.get().strip()
        nova, nova2 = self.campo_nova.get(), self.campo_nova2.get()
        if len(re.sub(r"\D", "", codigo)) != 6:
            _msg(self.aviso, "Digite os 6 números do código.")
            return
        problema = problemas_senha(nova, nova2)
        if problema:
            _msg(self.aviso, problema)
            return
        self.botao_redefinir.configure(state="disabled", text="Redefinindo...")

        def sucesso(texto):
            self.destroy()
            messagebox.showinfo("Senha redefinida", texto + "\n\nEntre com a nova senha.")

        def erro(e):
            self.botao_redefinir.configure(state="normal", text="Redefinir senha")
            _msg(self.aviso, str(e) if isinstance(e, ApiError) else "Não foi possível conectar à API.")

        rodar_em_background(self, lambda: self.api.redefinir_senha(self._ident, codigo, nova), sucesso, erro)


# --------------------------------------------------------------------------------------
# Trocar senha (voluntária ou obrigatória)
# --------------------------------------------------------------------------------------
class JanelaTrocarSenha(_JanelaModal):
    def __init__(self, master, api, obrigatoria=False, ao_concluir=None, ao_cancelar=None):
        super().__init__(master, "Trocar senha")
        self.api, self.obrigatoria = api, obrigatoria
        self._ao_concluir, self._ao_cancelar = ao_concluir, ao_cancelar
        self._concluida = False
        self.protocol("WM_DELETE_WINDOW", self.cancelar)
        i = self.interno
        ctk.CTkLabel(i, text="Defina uma nova senha" if obrigatoria else "Trocar senha",
                     font=ctk.CTkFont(size=18, weight="bold"), text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x")
        texto = ("Sua senha é provisória (ou fraca). Escolha uma senha só sua para continuar." if obrigatoria
                 else "Ao trocar, os outros aparelhos conectados com sua conta são desconectados.")
        ctk.CTkLabel(i, text=texto, font=ctk.CTkFont(size=12), text_color=tema.TEXTO_SUAVE, anchor="w",
                     justify="left", wraplength=340).pack(fill="x", pady=(4, 6))
        _rotulo(i, "Senha atual")
        self.campo_atual = _campo(i, senha=True)
        _rotulo(i, "Nova senha")
        self.campo_nova = _campo(i, senha=True)
        _rotulo(i, "Repita a nova senha")
        self.campo_nova2 = _campo(i, senha=True)
        self.campo_nova2.bind("<Return>", lambda _e: self.salvar())
        ctk.CTkLabel(i, text=DICA_SENHA, font=ctk.CTkFont(size=10), text_color=tema.TEXTO_SUAVE, anchor="w",
                     justify="left", wraplength=340).pack(fill="x", pady=(4, 0))
        self.aviso = ctk.CTkLabel(i, text="", font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=340)
        self.aviso.pack(fill="x", pady=(6, 0))
        self.botao = _botao(i, "Trocar senha", self.salvar)
        self.botao.pack(fill="x", pady=(10, 6))
        _botao(i, "Sair" if obrigatoria else "Cancelar", self.cancelar, principal=False).pack(fill="x")
        self.mostrar()
        self.after(200, self.campo_atual.focus)

    def salvar(self):
        atual, nova, nova2 = self.campo_atual.get(), self.campo_nova.get(), self.campo_nova2.get()
        if not atual:
            _msg(self.aviso, "Digite a senha atual.")
            return
        problema = problemas_senha(nova, nova2)
        if problema:
            _msg(self.aviso, problema)
            return
        if nova == atual:
            _msg(self.aviso, "A nova senha precisa ser diferente da atual.")
            return
        self.botao.configure(state="disabled", text="Salvando...")

        def sucesso(_):
            self._concluida = True
            self.destroy()
            messagebox.showinfo("Senha trocada", "Pronto! Sua senha foi trocada.")
            if self._ao_concluir:
                self._ao_concluir()

        def erro(e):
            self.botao.configure(state="normal", text="Trocar senha")
            _msg(self.aviso, str(e) if isinstance(e, ApiError) else "Não foi possível conectar à API.")

        rodar_em_background(self, lambda: self.api.trocar_senha(atual, nova), sucesso, erro)

    def cancelar(self):
        if self._concluida:
            return
        self._concluida = True
        self.destroy()
        if self._ao_cancelar:
            self._ao_cancelar()


# --------------------------------------------------------------------------------------
# Senha provisória (mostrada UMA vez) e cadastro de login
# --------------------------------------------------------------------------------------
class JanelaSenhaProvisoria(_JanelaModal):
    def __init__(self, master, nome, login, senha, titulo="Senha provisória"):
        super().__init__(master, titulo)
        i = self.interno
        ctk.CTkLabel(i, text=titulo, font=ctk.CTkFont(size=18, weight="bold"), text_color=tema.AZUL_ESCURO,
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(i, text=f"Entregue a {nome} pessoalmente (ou por um canal seguro). Ela só aparece agora, nesta janela. "
                             "No primeiro acesso a pessoa é obrigada a escolher uma senha própria.",
                     font=ctk.CTkFont(size=12), text_color=tema.TEXTO_SUAVE, anchor="w", justify="left",
                     wraplength=340).pack(fill="x", pady=(4, 8))
        _rotulo(i, "Login")
        ctk.CTkLabel(i, text=login or "—", font=ctk.CTkFont(size=14), text_color=tema.TEXTO, anchor="w").pack(fill="x")
        _rotulo(i, "Senha provisória")
        caixa = ctk.CTkFrame(i, fg_color=tema.AZUL_CLARO, corner_radius=8)
        caixa.pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(caixa, text=senha, font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
                     text_color=tema.AZUL_ESCURO).pack(padx=12, pady=10)
        self.botao_copiar = _botao(i, "Copiar senha", lambda: self._copiar(senha))
        self.botao_copiar.pack(fill="x", pady=(12, 6))
        _botao(i, "Fechar", self.destroy, principal=False).pack(fill="x")
        self.mostrar()

    def _copiar(self, senha):
        self.clipboard_clear()
        self.clipboard_append(senha)
        self.botao_copiar.configure(text="Copiada!")


class JanelaNovoLogin(_JanelaModal):
    """Cria o login de quem trabalha no SAAE. Sem senha digitada, o servidor gera uma provisória."""

    def __init__(self, master, api, ao_salvar):
        super().__init__(master, "Novo login da equipe", largura=440)
        self.api, self.ao_salvar = api, ao_salvar
        i = self.interno
        ctk.CTkLabel(i, text="Novo login da equipe", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=tema.AZUL_ESCURO, anchor="w").pack(fill="x")
        _rotulo(i, "Nome")
        self.campo_nome = _campo(i)
        _rotulo(i, "E-mail (recuperação de senha; obrigatório para administrador)")
        self.campo_email = _campo(i)
        _rotulo(i, "Telefone (também serve de login)")
        self.campo_telefone = _campo(i)
        _rotulo(i, "Tipo")
        self.combo_tipo = ctk.CTkOptionMenu(i, values=["tecnico", "operador_eta", "quimico", "operador", "admin"],
                                            height=36, fg_color=tema.AZUL, button_color=tema.AZUL_HOVER)
        self.combo_tipo.pack(fill="x", pady=(2, 0))
        _rotulo(i, "Localidade (obrigatória para técnico e operador de ETA)")
        self.combo_localidade = ctk.CTkOptionMenu(i, values=[LOCALIDADE_LABEL[k] for k in LOCALIDADE_LABEL],
                                                  height=36, fg_color=tema.AZUL, button_color=tema.AZUL_HOVER)
        self.combo_localidade.pack(fill="x", pady=(2, 0))
        _rotulo(i, "Senha inicial (opcional — deixe em branco para gerar uma provisória)")
        self.campo_senha = _campo(i, senha=True)
        self.aviso = ctk.CTkLabel(i, text="", font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=360)
        self.aviso.pack(fill="x", pady=(6, 0))
        self.botao = _botao(i, "Cadastrar", self.salvar)
        self.botao.pack(fill="x", pady=(10, 6))
        _botao(i, "Cancelar", self.destroy, principal=False).pack(fill="x")
        self.mostrar()

    def salvar(self):
        nome = self.campo_nome.get().strip()
        email = self.campo_email.get().strip()
        telefone = self.campo_telefone.get().strip()
        senha = self.campo_senha.get()
        tipo = self.combo_tipo.get()
        if not nome or not (email or telefone):
            _msg(self.aviso, "Preencha o nome e pelo menos o e-mail ou o telefone.")
            return
        if tipo == "admin" and not email:
            _msg(self.aviso, "Administrador precisa de e-mail (código de verificação e recuperação de senha).")
            return
        if senha:
            problema = problemas_senha(senha)
            if problema:
                _msg(self.aviso, problema)
                return
        localidade = next((k for k, v in LOCALIDADE_LABEL.items() if v == self.combo_localidade.get()), "sede")
        self.botao.configure(state="disabled", text="Cadastrando...")

        def sucesso(dados):
            login = email or telefone
            self.destroy()
            self.ao_salvar()
            if dados.get("senha_provisoria"):
                JanelaSenhaProvisoria(self._master, nome, login, dados["senha_provisoria"], "Login criado")
            else:
                messagebox.showinfo("Pronto", f"Cadastrado! Login: {login}\nNo primeiro acesso a pessoa precisará trocar a senha.")

        def erro(e):
            self.botao.configure(state="normal", text="Cadastrar")
            _msg(self.aviso, str(e) if isinstance(e, ApiError) else "Falha ao cadastrar.")

        rodar_em_background(self, lambda: self.api.cadastrar_usuario_login(nome, telefone, senha, tipo, localidade, email), sucesso, erro)


# --------------------------------------------------------------------------------------
# Tela: Acessos (lista de contas, reset de senha)
# --------------------------------------------------------------------------------------
class TelaAcessos(ctk.CTkFrame):
    def __init__(self, master, api):
        super().__init__(master, fg_color="transparent")
        self.api = api
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 6))
        ctk.CTkLabel(topo, text="Acessos e senhas", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=tema.AZUL_ESCURO).pack(side="left")
        ctk.CTkButton(topo, text="+ Novo login", width=110, command=self.novo_login).pack(side="right", padx=(10, 0))
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        filtros = ctk.CTkFrame(self, fg_color="transparent")
        filtros.pack(fill="x", padx=20, pady=(0, 6))
        self.busca = ctk.CTkEntry(filtros, width=280, height=34, placeholder_text="Buscar por nome, e-mail ou telefone",
                                  border_color=tema.LINHA, fg_color="white", text_color=tema.TEXTO)
        self.busca.pack(side="left")
        self.busca.bind("<Return>", lambda _e: self.carregar())
        self.tipos = ["Todos"] + [TIPO_USUARIO_LABEL[t] for t in TIPO_USUARIO_LABEL]
        self.combo_tipo = ctk.CTkOptionMenu(filtros, values=self.tipos, width=190, height=34, command=lambda _v: self.carregar(),
                                            fg_color=tema.AZUL, button_color=tema.AZUL_HOVER)
        self.combo_tipo.pack(side="left", padx=10)
        ctk.CTkLabel(self, text="Senha esquecida? A pessoa usa \"Esqueci minha senha\" (código por e-mail). Para quem não tem "
                                "e-mail cadastrado, use \"Resetar senha\": gera uma senha provisória que ela é obrigada a trocar.",
                     font=ctk.CTkFont(size=11), text_color=tema.TEXTO_SUAVE, anchor="w", justify="left",
                     wraplength=900).pack(fill="x", padx=22, pady=(0, 4))

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=6)
        self.carregar()

    def novo_login(self):
        JanelaNovoLogin(self.winfo_toplevel(), self.api, self.carregar)

    def carregar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)
        escolhido = self.combo_tipo.get()
        tipo = next((k for k, v in TIPO_USUARIO_LABEL.items() if v == escolhido), None)
        busca = self.busca.get().strip()

        def sucesso(usuarios):
            for w in self.lista.winfo_children():
                w.destroy()
            if not usuarios:
                ctk.CTkLabel(self.lista, text="Nenhum usuário encontrado.").pack(pady=20)
                return
            for u in usuarios:
                self._linha(u)

        def erro(e):
            for w in self.lista.winfo_children():
                w.destroy()
            ctk.CTkLabel(self.lista, text=str(e) if isinstance(e, ApiError) else "Falha ao carregar usuários.",
                         text_color=tema.ERRO).pack(pady=20)

        rodar_em_background(self, lambda: self.api.listar_usuarios(tipo, busca), sucesso, erro)

    def _linha(self, u):
        linha = ctk.CTkFrame(self.lista, corner_radius=10, fg_color="white", border_width=1, border_color=tema.LINHA)
        linha.pack(fill="x", pady=3)
        bloco = ctk.CTkFrame(linha, fg_color="transparent")
        bloco.pack(side="left", fill="x", expand=True, padx=12, pady=8)
        ctk.CTkLabel(bloco, text=u["nome"], font=ctk.CTkFont(size=13, weight="bold"), text_color=tema.TEXTO,
                     anchor="w").pack(fill="x")
        contato = " · ".join(x for x in (u.get("email"), u.get("telefone")) if x) or "sem e-mail nem telefone"
        local = LOCALIDADE_LABEL.get(u.get("localidade"))
        ctk.CTkLabel(bloco, text=f"{TIPO_USUARIO_LABEL.get(u['tipo'], u['tipo'])} · {contato}" + (f" · {local}" if local else ""),
                     font=ctk.CTkFont(size=11), text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x")
        if not u.get("email"):
            ctk.CTkLabel(bloco, text="sem e-mail: não consegue recuperar a senha sozinho(a)", font=ctk.CTkFont(size=10),
                         text_color=tema.AMBAR, anchor="w").pack(fill="x")
        selos = ctk.CTkFrame(linha, fg_color="transparent", width=1, height=1)
        if u.get("bloqueado") or u.get("trocar_senha"):
            selos.pack(side="left", padx=6)
        if u.get("bloqueado"):
            ctk.CTkLabel(selos, text="BLOQUEADO", font=ctk.CTkFont(size=10, weight="bold"), text_color=tema.ERRO,
                         fg_color=tema.ERRO_FUNDO, corner_radius=8).pack(pady=2, ipadx=6)
        if u.get("trocar_senha"):
            ctk.CTkLabel(selos, text="TROCA PENDENTE", font=ctk.CTkFont(size=10, weight="bold"), text_color=tema.AMBAR,
                         fg_color=tema.AMBAR_FUNDO, corner_radius=8).pack(pady=2, ipadx=6)
        ctk.CTkButton(linha, text="Resetar senha", width=120, height=32, fg_color="white", text_color=tema.AZUL,
                      border_width=1, border_color=tema.AZUL, hover_color=tema.AZUL_CLARO,
                      command=lambda x=u: self.resetar(x)).pack(side="right", padx=12)

    def resetar(self, u):
        if not messagebox.askyesno(
                "Resetar senha",
                f"Gerar uma senha provisória para {u['nome']}?\n\nA senha atual deixa de valer e a pessoa é desconectada "
                "de todos os aparelhos. No próximo acesso ela será obrigada a trocar a senha."):
            return

        def sucesso(dados):
            JanelaSenhaProvisoria(self.winfo_toplevel(), u["nome"], u.get("email") or u.get("telefone"),
                                  dados["senha_provisoria"], "Senha resetada")
            self.carregar()

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao resetar a senha.")

        rodar_em_background(self, lambda: self.api.resetar_senha_usuario(u["id"]), sucesso, erro)


# --------------------------------------------------------------------------------------
# Tela: Auditoria
# --------------------------------------------------------------------------------------
ACAO_LABEL = {
    "login_ok": "Entrou", "login_falhou": "Senha errada", "login_bloqueado": "Tentou entrar com conta bloqueada",
    "conta_bloqueada": "Conta bloqueada (muitas tentativas)", "logout": "Saiu", "logout_todos": "Saiu de todos os aparelhos",
    "2fa_enviado": "Código de verificação enviado", "2fa_falhou": "Código de verificação errado",
    "recuperacao_pedida": "Pediu recuperação de senha", "recuperacao_codigo_errado": "Código de recuperação errado",
    "recuperacao_sem_conta_ou_email": "Recuperação pedida sem conta/e-mail", "senha_redefinida": "Senha redefinida (código)",
    "senha_trocada": "Trocou a senha", "troca_senha_falhou": "Troca de senha falhou (senha atual errada)",
    "senha_resetada_por_admin": "Admin resetou a senha de alguém", "usuario_criado": "Login criado",
    "registro": "Morador criou conta", "refresh_reutilizado": "ALERTA: sessão reutilizada (possível roubo)",
}
ACOES_SUSPEITAS = {"login_falhou", "login_bloqueado", "conta_bloqueada", "2fa_falhou", "recuperacao_codigo_errado",
                   "troca_senha_falhou", "refresh_reutilizado", "recuperacao_sem_conta_ou_email"}


def _hora_local(texto):
    try:
        dt = datetime.fromisoformat(texto)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # o servidor guarda em UTC
        return dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
    except Exception:
        return texto or ""


class TelaAuditoria(ctk.CTkFrame):
    def __init__(self, master, api):
        super().__init__(master, fg_color="transparent")
        self.api = api
        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 6))
        ctk.CTkLabel(topo, text="Auditoria de segurança", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=tema.AZUL_ESCURO).pack(side="left")
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")
        self.opcoes = ["Todos os eventos", "Só os suspeitos"] + [ACAO_LABEL[k] for k in ACAO_LABEL]
        self.combo = ctk.CTkOptionMenu(topo, values=self.opcoes, width=300, height=34, command=lambda _v: self._filtrar(),
                                       fg_color=tema.AZUL, button_color=tema.AZUL_HOVER)
        self.combo.pack(side="right", padx=10)
        ctk.CTkLabel(self, text="Quem entrou, senhas erradas, bloqueios, trocas e resets de senha. Os horários estão no fuso deste computador.",
                     font=ctk.CTkFont(size=11), text_color=tema.TEXTO_SUAVE, anchor="w").pack(fill="x", padx=22)
        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=8)
        self._eventos = []
        self.carregar()

    def carregar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(eventos):
            self._eventos = eventos
            self._filtrar()

        def erro(e):
            for w in self.lista.winfo_children():
                w.destroy()
            ctk.CTkLabel(self.lista, text=str(e) if isinstance(e, ApiError) else "Falha ao carregar a auditoria.",
                         text_color=tema.ERRO).pack(pady=20)

        rodar_em_background(self, lambda: self.api.listar_auditoria(limite=500), sucesso, erro)

    def _filtrar(self):
        escolha = self.combo.get()
        eventos = self._eventos
        if escolha == "Só os suspeitos":
            eventos = [e for e in eventos if e["acao"] in ACOES_SUSPEITAS]
        elif escolha != "Todos os eventos":
            acao = next((k for k, v in ACAO_LABEL.items() if v == escolha), None)
            eventos = [e for e in eventos if e["acao"] == acao]
        for w in self.lista.winfo_children():
            w.destroy()
        if not eventos:
            ctk.CTkLabel(self.lista, text="Nenhum evento.").pack(pady=20)
            return
        for e in eventos:
            suspeito = e["acao"] in ACOES_SUSPEITAS
            linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color=tema.ERRO_FUNDO if suspeito else "white",
                                 border_width=1, border_color=tema.LINHA)
            linha.pack(fill="x", pady=2)
            ctk.CTkLabel(linha, text=_hora_local(e["quando"]), width=150, anchor="w", font=ctk.CTkFont(size=11),
                         text_color=tema.TEXTO_SUAVE).pack(side="left", padx=(10, 4), pady=6)
            ctk.CTkLabel(linha, text=ACAO_LABEL.get(e["acao"], e["acao"]), width=290, anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=tema.ERRO if suspeito else tema.TEXTO).pack(side="left", padx=4)
            ctk.CTkLabel(linha, text=e.get("identificador") or (f"usuário {e['usuario_id']}" if e.get("usuario_id") else "—"),
                         width=190, anchor="w", font=ctk.CTkFont(size=11), text_color=tema.TEXTO).pack(side="left", padx=4)
            extra = " · ".join(x for x in (e.get("ip"), e.get("detalhe")) if x)
            ctk.CTkLabel(linha, text=extra, anchor="w", font=ctk.CTkFont(size=10), text_color=tema.TEXTO_SUAVE,
                         wraplength=330, justify="left").pack(side="left", padx=4, fill="x", expand=True)
