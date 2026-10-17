"""SIGA — Painel do Químico (programa separado, para Windows).

Tem login próprio, só para quem é Químico (e Administrador, para suporte), e mostra apenas a
Área do Químico: conformidade com a Portaria GM/MS 888/2021, análises da ETA, coletas e resultados,
laudos e pontos/regras. O Painel do Administrador (main.py) continua separado.

Rodar:  python main_quimico.py      (ou dê dois cliques em iniciar_painel_quimico.bat)
"""
import customtkinter as ctk

import janelas_frente
janelas_frente.instalar()  # janelas secundárias e avisos sempre na frente (Windows)

import tema
from api_client import ApiClient
from area_quimico import AreaQuimico
from layout_comum import TelaSplash, TelaLoginBase, barra_superior, pilula, rodape

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
ctk.ThemeManager.theme["CTkButton"]["fg_color"] = [tema.AZUL, tema.AZUL]
ctk.ThemeManager.theme["CTkButton"]["hover_color"] = [tema.AZUL_HOVER, tema.AZUL_HOVER]

TITULO = "SIGA — Químico"
SUBTITULO = "Qualidade da água · Portaria GM/MS 888/2021"
TIPOS_ACEITOS = ("quimico", "admin")


class TelaLoginQuimico(TelaLoginBase):
    def __init__(self, master, api, ao_logar):
        super().__init__(
            master, api, ao_logar, titulo_cartao="Painel do Químico", subtitulo_cartao="SAAE de Chalé",
            aviso="Acesso restrito ao químico responsável — use o e-mail ou telefone e a senha do seu cadastro.",
            tipos_aceitos=TIPOS_ACEITOS,
            msg_negado="Este painel é exclusivo do químico. Use o Painel do Administrador para as demais áreas.",
            titulo_barra=TITULO, subtitulo_barra=SUBTITULO,
        )


class PainelQuimico(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SIGA — Painel do Químico — SAAE de Chalé")
        self.geometry("1180x720")
        self.minsize(1000, 600)
        self.configure(fg_color=tema.FUNDO)
        self.api = ApiClient()
        self.tela_splash = TelaSplash(self, self.ir_login, titulo="Painel do Químico", prefixo="SIGA · ",
                                      subtitulo="Qualidade da água · Portaria GM/MS 888/2021")
        self.tela_splash.pack(fill="both", expand=True)
        self.tela_login = self.tela_painel = None

    def ir_login(self):
        self._esconder()
        if self.api.token:
            from async_helper import rodar_em_background
            rodar_em_background(self, self.api.sair)
        self.api = ApiClient()
        self.tela_login = TelaLoginQuimico(self, self.api, self.ir_painel)
        self.tela_login.pack(fill="both", expand=True)

    def _esconder(self):
        for t in (self.tela_splash, self.tela_login, self.tela_painel):
            if t is not None and t.winfo_exists():
                t.pack_forget()

    def ir_painel(self):
        self._esconder()
        self.tela_painel = quadro = ctk.CTkFrame(self, fg_color=tema.FUNDO, corner_radius=0)
        quadro.pack(fill="both", expand=True)
        quadro.grid_columnconfigure(0, weight=1)
        quadro.grid_rowconfigure(1, weight=1)
        barra = barra_superior(quadro, TITULO, SUBTITULO)
        barra.grid(row=0, column=0, sticky="ew")
        pilula(barra.menu, "Qualidade da água", lambda: None, ativa=True).pack(side="left", padx=2)
        pilula(barra.menu, "Trocar senha", self.trocar_senha, tamanho=12).pack(side="left", padx=(10, 0))
        pilula(barra.menu, "Sair", self.sair, tamanho=12).pack(side="left", padx=(4, 0))
        AreaQuimico(quadro, self.api).grid(row=1, column=0, sticky="nsew")
        rodape(quadro).grid(row=2, column=0, sticky="ew")

    def trocar_senha(self):
        from seguranca_painel import JanelaTrocarSenha
        JanelaTrocarSenha(self, self.api, obrigatoria=False)

    def sair(self):
        self.tela_painel.destroy()
        self.tela_painel = None
        self.ir_login()


if __name__ == "__main__":
    PainelQuimico().mainloop()
