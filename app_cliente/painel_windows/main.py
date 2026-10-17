import os
import subprocess
import json
from datetime import datetime, timedelta
import customtkinter as ctk
from tkinter import messagebox, filedialog, simpledialog
from PIL import Image as ImagemPIL

from api_client import ApiClient, ApiError
from async_helper import rodar_em_background

import sys

if getattr(sys, "frozen", False):
    # Rodando como .exe empacotado pelo PyInstaller — os arquivos de dados
    # (--add-data) ficam extraídos em sys._MEIPASS, não ao lado do script.
    PASTA_BASE = sys._MEIPASS
else:
    PASTA_BASE = os.path.dirname(os.path.abspath(__file__))
PASTA_ASSETS = os.path.join(PASTA_BASE, "assets")


class TelaSplash(ctk.CTkFrame):
    """Mostra o logo por alguns segundos antes de ir pro login."""

    def __init__(self, master, ao_terminar, duracao_ms=10500):
        super().__init__(master, fg_color="#f0f9fb")

        caminho_logo = os.path.join(PASTA_ASSETS, "logo_splash.png")
        if os.path.exists(caminho_logo):
            imagem_pil = ImagemPIL.open(caminho_logo)
            imagem_ctk = ctk.CTkImage(light_image=imagem_pil, dark_image=imagem_pil, size=(320, 320))
            ctk.CTkLabel(self, image=imagem_ctk, text="").pack(expand=True)
        else:
            ctk.CTkLabel(
                self, text="💧 SIGA", font=ctk.CTkFont(size=48, weight="bold"), text_color="#0891b2"
            ).pack(expand=True)

        self.after(duracao_ms, ao_terminar)

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

COR_PRINCIPAL = "#0891b2"  # azul-água, mesma paleta do projeto original

STATUS_LABEL = {
    "aberto": "Aberto",
    "atribuido": "Atribuído",
    "em_andamento": "Em andamento",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
}

TIPO_LABEL = {
    "vazamento": "Vazamento",
    "manutencao": "Manutenção",
    "religacao": "Religação",
    "vistoria": "Vistoria",
    "outro": "Outro",
}

LOCALIDADE_LABEL = {
    "sede": "Chalé (sede)",
    "penha_do_coco": "Penha do Coco",
    "bananal": "Bananal",
    "agua_limpa": "Água Limpa",
}
LOCALIDADES = list(LOCALIDADE_LABEL.keys())


class TelaLogin(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient, ao_logar):
        super().__init__(master)
        self.api = api
        self.ao_logar = ao_logar

        # Marca d'água do logo, bem sutil (baixa opacidade) — só decoração,
        # não pode atrapalhar a leitura do formulário por cima dela.
        caminho_logo = os.path.join(PASTA_ASSETS, "logo_splash.png")
        if os.path.exists(caminho_logo):
            try:
                logo_original = ImagemPIL.open(caminho_logo).convert("RGBA")
                canal_alfa = logo_original.split()[3].point(lambda p: int(p * 0.06))
                logo_original.putalpha(canal_alfa)
                imagem_marca_dagua = ctk.CTkImage(light_image=logo_original, dark_image=logo_original, size=(480, 480))
                ctk.CTkLabel(self, image=imagem_marca_dagua, text="").place(relx=0.5, rely=0.5, anchor="center")
            except Exception:
                pass  # decoração é opcional — se der qualquer problema, só não mostra, sem travar o login

        container = ctk.CTkFrame(self, corner_radius=12)
        container.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            container, text="SIGA", font=ctk.CTkFont(size=28, weight="bold"), text_color=COR_PRINCIPAL
        ).grid(row=0, column=0, columnspan=2, padx=40, pady=(30, 0))
        ctk.CTkLabel(
            container, text="Sistema Integrado de Gestão de Água e Esgoto", font=ctk.CTkFont(size=12)
        ).grid(row=1, column=0, columnspan=2, padx=40, pady=(0, 5))
        self.label_empresa = ctk.CTkLabel(container, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.label_empresa.grid(row=2, column=0, columnspan=2, padx=40, pady=(0, 5))
        ctk.CTkLabel(container, text="Painel do operador", font=ctk.CTkFont(size=12), text_color="gray").grid(
            row=3, column=0, columnspan=2, padx=40, pady=(0, 20)
        )
        rodar_em_background(self, self.api.obter_empresa, self._exibir_nome_empresa, lambda e: None)

        ctk.CTkLabel(container, text="E-mail ou telefone").grid(row=4, column=0, columnspan=2, sticky="w", padx=40)
        self.campo_usuario = ctk.CTkEntry(container, width=260)
        self.campo_usuario.grid(row=5, column=0, columnspan=2, padx=40, pady=(0, 15))

        ctk.CTkLabel(container, text="Senha").grid(row=6, column=0, columnspan=2, sticky="w", padx=40)
        self.campo_senha = ctk.CTkEntry(container, width=260, show="*")
        self.campo_senha.grid(row=7, column=0, columnspan=2, padx=40, pady=(0, 20))
        self.campo_senha.bind("<Return>", lambda e: self.entrar())

        self.botao_entrar = ctk.CTkButton(
            container, text="Entrar", fg_color=COR_PRINCIPAL, command=self.entrar
        )
        self.botao_entrar.grid(row=8, column=0, columnspan=2, padx=40, pady=(0, 30), sticky="ew")

    def _exibir_nome_empresa(self, empresa):
        if empresa and empresa.get("nome_fantasia") and empresa["nome_fantasia"] != "SIGA":
            self.label_empresa.configure(text=empresa["nome_fantasia"])

    def entrar(self):
        usuario = self.campo_usuario.get().strip()
        senha = self.campo_senha.get()
        self.botao_entrar.configure(state="disabled", text="Entrando...")

        def fazer_login():
            return self.api.login(usuario, senha)

        def sucesso(dados):
            self.botao_entrar.configure(state="normal", text="Entrar")
            if self.api.tipo_usuario not in ("admin", "operador"):
                messagebox.showerror("Acesso negado", "Este painel é apenas para admin/operador.")
                return
            self.ao_logar()

        def erro(e):
            self.botao_entrar.configure(state="normal", text="Entrar")
            if isinstance(e, ApiError):
                messagebox.showerror("Erro no login", str(e))
            else:
                messagebox.showerror("Erro", "Não foi possível conectar à API. Verifique o endereço configurado.")

        rodar_em_background(self, fazer_login, sucesso, erro)


class LinhaChamado(ctk.CTkFrame):
    def __init__(self, master, chamado, tecnicos, api: ApiClient, ao_atualizar):
        super().__init__(master, corner_radius=8, fg_color="#f1f5f9")
        self.chamado = chamado
        self.api = api
        self.ao_atualizar = ao_atualizar

        self.grid_columnconfigure(1, weight=1)

        cor_status = {
            "aberto": "#dc2626",
            "atribuido": "#d97706",
            "em_andamento": "#2563eb",
            "concluido": "#16a34a",
            "cancelado": "#6b7280",
        }.get(chamado["status"], "#6b7280")

        ctk.CTkLabel(
            self, text=f"#{chamado['id']}", font=ctk.CTkFont(weight="bold"), width=50
        ).grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")

        texto = f"{TIPO_LABEL.get(chamado['tipo'], chamado['tipo'])} — Cliente #{chamado['cliente_id']}"
        local_atendimento = chamado.get("local_atendimento")
        if local_atendimento:
            texto += f" — {LOCALIDADE_LABEL.get(local_atendimento, local_atendimento)}"
        ctk.CTkLabel(self, text=texto, anchor="w").grid(row=0, column=1, sticky="ew", pady=10)

        ctk.CTkLabel(
            self, text=STATUS_LABEL.get(chamado["status"], chamado["status"]), text_color=cor_status,
            font=ctk.CTkFont(weight="bold"),
        ).grid(row=0, column=2, padx=10)

        if chamado["status"] == "aberto":
            # Prioriza técnicos da mesma localidade do chamado; se não tiver
            # nenhum lá, mostra todos (melhor atribuir de outra unidade do
            # que deixar o chamado parado).
            tecnicos_da_localidade = [t for t in tecnicos if t.get("localidade") == local_atendimento]
            tecnicos_para_mostrar = tecnicos_da_localidade or tecnicos

            nomes_tecnicos = [t["nome"] for t in tecnicos_para_mostrar] or ["(nenhum técnico cadastrado)"]
            self.combo_tecnico = ctk.CTkOptionMenu(self, values=nomes_tecnicos, width=180)
            self.combo_tecnico.grid(row=0, column=3, padx=5)
            self.tecnicos = tecnicos_para_mostrar

            if not tecnicos_da_localidade and local_atendimento:
                ctk.CTkLabel(
                    self, text="⚠ sem técnico local", text_color="#d97706", font=ctk.CTkFont(size=10)
                ).grid(row=1, column=3, sticky="w", padx=5)

            ctk.CTkButton(
                self, text="Atribuir", width=90, fg_color=COR_PRINCIPAL, command=self.atribuir
            ).grid(row=0, column=4, padx=(5, 10))
        else:
            nome_tecnico = next((t["nome"] for t in tecnicos if t["id"] == chamado.get("tecnico_id")), "—")
            ctk.CTkLabel(self, text=f"Técnico: {nome_tecnico}").grid(row=0, column=3, padx=10)

        self.botao_pdf = ctk.CTkButton(
            self, text="📄 PDF", width=70, fg_color="#6b7280", hover_color="#4b5563", command=self.gerar_pdf
        )
        self.botao_pdf.grid(row=0, column=5, padx=(5, 10))

    def gerar_pdf(self):
        self.botao_pdf.configure(state="disabled", text="Gerando...")

        def buscar_pdf():
            return self.api.baixar_relatorio_pdf(self.chamado["id"])

        def sucesso(pdf_bytes):
            self.botao_pdf.configure(state="normal", text="📄 PDF")
            caminho = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                initialfile=f"chamado_{self.chamado['id']}.pdf",
                filetypes=[("PDF", "*.pdf")],
            )
            if not caminho:
                return
            with open(caminho, "wb") as f:
                f.write(pdf_bytes)
            try:
                os.startfile(caminho)  # abre automaticamente no Windows
            except Exception:
                messagebox.showinfo("Salvo", f"PDF salvo em: {caminho}")

        def erro(e):
            self.botao_pdf.configure(state="normal", text="📄 PDF")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao gerar PDF")

        rodar_em_background(self, buscar_pdf, sucesso, erro)

    def atribuir(self):
        nome_escolhido = self.combo_tecnico.get()
        tecnico = next((t for t in self.tecnicos if t["nome"] == nome_escolhido), None)
        if not tecnico:
            messagebox.showwarning("Atenção", "Cadastre um técnico antes de atribuir.")
            return

        def fazer_atribuicao():
            return self.api.atribuir_tecnico(self.chamado["id"], tecnico["id"])

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao atribuir técnico")

        rodar_em_background(self, fazer_atribuicao, lambda _: self.ao_atualizar(), erro)


class TelaChamados(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Chamados", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")

        self.filtro = ctk.CTkOptionMenu(
            topo, values=["Todos", "Aberto", "Atribuído", "Em andamento", "Concluído"], command=lambda _: self.carregar()
        )
        self.filtro.pack(side="right")

        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right", padx=10)

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def carregar(self):
        for widget in self.lista.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        status_map = {
            "Todos": None, "Aberto": "aberto", "Atribuído": "atribuido",
            "Em andamento": "em_andamento", "Concluído": "concluido",
        }
        status = status_map.get(self.filtro.get())

        def buscar_dados():
            return self.api.listar_chamados(status=status), self.api.listar_tecnicos()

        def sucesso(resultado):
            chamados, tecnicos = resultado
            for widget in self.lista.winfo_children():
                widget.destroy()

            if not chamados:
                ctk.CTkLabel(self.lista, text="Nenhum chamado encontrado.").pack(pady=20)
                return

            for chamado in chamados:
                linha = LinhaChamado(self.lista, chamado, tecnicos, self.api, self.carregar)
                linha.pack(fill="x", pady=4)

        def erro(e):
            for widget in self.lista.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar chamados")

        rodar_em_background(self, buscar_dados, sucesso, erro)


class TelaDashboard(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        ctk.CTkLabel(self, text="Dashboard", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", padx=20, pady=(20, 10)
        )

        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.pack(fill="x", padx=20)

        self.carregar()

    def _card(self, parent, titulo, valor, cor):
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color=cor)
        ctk.CTkLabel(card, text=str(valor), font=ctk.CTkFont(size=28, weight="bold"), text_color="white").pack(
            pady=(15, 0)
        )
        ctk.CTkLabel(card, text=titulo, text_color="white").pack(pady=(0, 15), padx=15)
        return card

    def carregar(self):
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.cards_frame, text="Carregando...").pack(pady=20)

        def sucesso(resumo):
            for widget in self.cards_frame.winfo_children():
                widget.destroy()

            self._card(self.cards_frame, "Chamados em aberto", resumo["chamados_em_aberto"], "#dc2626").pack(
                side="left", expand=True, fill="both", padx=(0, 10)
            )
            self._card(self.cards_frame, "Chamados concluídos", resumo["chamados_concluidos"], "#16a34a").pack(
                side="left", expand=True, fill="both", padx=10
            )

            por_tipo = resumo["por_tipo"]
            texto_tipos = "  •  ".join(f"{TIPO_LABEL[t]}: {q}" for t, q in por_tipo.items())
            ctk.CTkLabel(self, text=texto_tipos, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=20)

        def erro(e):
            for widget in self.cards_frame.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar dashboard")

        rodar_em_background(self, self.api.relatorio_resumo, sucesso, erro)


class JanelaNovoItem(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar):
        super().__init__(master)
        self.title("Novo item de estoque")
        self.geometry("360x360")
        self.api = api
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="Nome do item").pack(anchor="w", padx=20, pady=(20, 0))
        self.campo_nome = ctk.CTkEntry(self, width=300)
        self.campo_nome.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Unidade de medida (un, m, kg, l...)").pack(anchor="w", padx=20)
        self.campo_unidade = ctk.CTkEntry(self, width=300)
        self.campo_unidade.insert(0, "un")
        self.campo_unidade.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Valor unitário (R$)").pack(anchor="w", padx=20)
        self.campo_valor = ctk.CTkEntry(self, width=300)
        self.campo_valor.insert(0, "0")
        self.campo_valor.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Estoque mínimo (alerta)").pack(anchor="w", padx=20)
        self.campo_minimo = ctk.CTkEntry(self, width=300)
        self.campo_minimo.insert(0, "0")
        self.campo_minimo.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Cadastrar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do item.")
            return
        try:
            valor = float(self.campo_valor.get().replace(",", "."))
            minimo = float(self.campo_minimo.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Atenção", "Valor e estoque mínimo precisam ser números.")
            return

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def salvar_item():
            return self.api.criar_item_estoque(nome, self.campo_unidade.get().strip() or "un", valor, minimo)

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Cadastrar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao cadastrar item")

        rodar_em_background(self, salvar_item, sucesso, erro)


class JanelaMovimentar(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, itens, tecnicos, ao_salvar):
        super().__init__(master)
        self.title("Movimentar estoque")
        self.geometry("380x480")
        self.api = api
        self.itens = itens
        self.ao_salvar = ao_salvar

        # Mapa "texto mostrado" -> (tipo, valor), incluindo localidades e técnicos
        self.opcoes_local = {}
        for loc in LOCALIDADES:
            self.opcoes_local[LOCALIDADE_LABEL[loc]] = ("sede" if loc == "sede" else "unidade", loc)
        for tec in tecnicos:
            self.opcoes_local[f"Técnico: {tec['nome']}"] = ("tecnico", str(tec["id"]))

        nomes_itens = [i["nome"] for i in itens] or ["(cadastre um item primeiro)"]
        opcoes_texto = list(self.opcoes_local.keys())

        ctk.CTkLabel(self, text="Item").pack(anchor="w", padx=20, pady=(20, 0))
        self.combo_item = ctk.CTkOptionMenu(self, values=nomes_itens, width=320)
        self.combo_item.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Tipo de movimentação").pack(anchor="w", padx=20)
        self.combo_tipo = ctk.CTkOptionMenu(
            self, values=["entrada (compra → sede)", "transferência (origem → destino)", "ajuste (correção na origem)"],
            width=320,
        )
        self.combo_tipo.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Quantidade").pack(anchor="w", padx=20)
        self.campo_quantidade = ctk.CTkEntry(self, width=320)
        self.campo_quantidade.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Origem (de onde sai — sede, unidade ou técnico)").pack(anchor="w", padx=20)
        self.combo_origem = ctk.CTkOptionMenu(self, values=opcoes_texto, width=320)
        self.combo_origem.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Destino (pra onde vai — unidade ou técnico)").pack(anchor="w", padx=20)
        self.combo_destino = ctk.CTkOptionMenu(self, values=opcoes_texto, width=320)
        self.combo_destino.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Registrar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        nome_item = self.combo_item.get()
        item = next((i for i in self.itens if i["nome"] == nome_item), None)
        if not item:
            messagebox.showwarning("Atenção", "Cadastre um item antes de movimentar.")
            return
        try:
            quantidade = float(self.campo_quantidade.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Atenção", "Quantidade precisa ser um número.")
            return

        origem_tipo, origem_valor = self.opcoes_local.get(self.combo_origem.get(), (None, None))
        destino_tipo, destino_valor = self.opcoes_local.get(self.combo_destino.get(), (None, None))

        tipo_escolhido = self.combo_tipo.get()
        if tipo_escolhido.startswith("entrada"):
            tipo = "entrada"
            origem_tipo, origem_valor = None, None
            destino_tipo, destino_valor = "sede", "sede"
        elif tipo_escolhido.startswith("transferência"):
            tipo = "transferencia"
        else:
            tipo = "ajuste"
            destino_tipo, destino_valor = None, None

        self.botao_salvar.configure(state="disabled", text="Registrando...")

        def registrar():
            return self.api.movimentar_estoque(
                item["id"], tipo, quantidade, origem_tipo, origem_valor, destino_tipo, destino_valor
            )

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Registrar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao registrar movimentação")

        rodar_em_background(self, registrar, sucesso, erro)


class JanelaEditarItem(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, item, ao_salvar):
        super().__init__(master)
        self.title(f"Editar item — {item['nome']}")
        self.geometry("360x400")
        self.api = api
        self.item = item
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="Nome do item").pack(anchor="w", padx=20, pady=(20, 0))
        self.campo_nome = ctk.CTkEntry(self, width=300)
        self.campo_nome.insert(0, item["nome"])
        self.campo_nome.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Unidade de medida (un, m, kg, l...)").pack(anchor="w", padx=20)
        self.campo_unidade = ctk.CTkEntry(self, width=300)
        self.campo_unidade.insert(0, item["unidade_medida"])
        self.campo_unidade.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Valor unitário (R$)").pack(anchor="w", padx=20)
        self.campo_valor = ctk.CTkEntry(self, width=300)
        self.campo_valor.insert(0, str(item["valor_unitario"]))
        self.campo_valor.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Estoque mínimo (alerta)").pack(anchor="w", padx=20)
        self.campo_minimo = ctk.CTkEntry(self, width=300)
        self.campo_minimo.insert(0, str(item["estoque_minimo"]))
        self.campo_minimo.pack(padx=20, pady=(0, 15))

        linha_botoes = ctk.CTkFrame(self, fg_color="transparent")
        linha_botoes.pack(padx=20, pady=10, fill="x")
        self.botao_salvar = ctk.CTkButton(linha_botoes, text="Salvar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(
            linha_botoes, text="Desativar", fg_color="#dc2626", hover_color="#991b1b", width=100,
            command=self.desativar,
        ).pack(side="right")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do item.")
            return
        try:
            valor = float(self.campo_valor.get().replace(",", "."))
            minimo = float(self.campo_minimo.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Atenção", "Valor e estoque mínimo precisam ser números.")
            return

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def atualizar():
            return self.api.atualizar_item_estoque(self.item["id"], nome, self.campo_unidade.get().strip() or "un", valor, minimo)

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Salvar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao atualizar item")

        rodar_em_background(self, atualizar, sucesso, erro)

    def desativar(self):
        if not messagebox.askyesno(
            "Confirmar", f"Desativar o item '{self.item['nome']}'? "
            "Ele some da lista ativa, mas o histórico de movimentações continua intacto."
        ):
            return

        def fazer():
            return self.api.desativar_item_estoque(self.item["id"])

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao desativar item")

        rodar_em_background(self, fazer, sucesso, erro)


class JanelaManutencoesEta(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient):
        super().__init__(master)
        self.title("Manutenções da ETA")
        self.geometry("560x500")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(topo, text="Histórico de manutenções", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=15, pady=10)

        self.carregar()

    def carregar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(manutencoes):
            for w in self.lista.winfo_children():
                w.destroy()
            if not manutencoes:
                ctk.CTkLabel(self.lista, text="Nenhuma manutenção registrada ainda.").pack(pady=20)
                return
            for m in manutencoes:
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)
                data = datetime.fromisoformat(m["criado_em"]).strftime("%d/%m/%Y %H:%M")
                localidade_texto = LOCALIDADE_LABEL.get(m["localidade"], m["localidade"])
                tipo_texto = {
                    "limpeza_tanque": "Limpeza de tanque", "verificacao_cloro": "Verificação de cloro",
                    "manutencao_bomba": "Manutenção de bomba", "outro": "Outro",
                }.get(m["tipo"], m["tipo"])
                texto = f"[{data}] {localidade_texto} — {tipo_texto}\n{m['descricao']}"
                ctk.CTkLabel(linha, text=texto, anchor="w", justify="left").pack(padx=10, pady=8, fill="x")

        def erro(e):
            for w in self.lista.winfo_children():
                w.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar manutenções")

        rodar_em_background(self, self.api.listar_manutencoes_eta, sucesso, erro)


class JanelaAnalisesEta(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient):
        super().__init__(master)
        self.title("Análises diárias da ETA")
        self.geometry("640x560")
        self.api = api
        self.somente_nao_conformes = False

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=15, pady=(15, 5))
        ctk.CTkLabel(topo, text="Análises registradas", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        self.botao_filtro = ctk.CTkButton(topo, text="Mostrar só fora do padrão", width=180, command=self.alternar_filtro)
        self.botao_filtro.pack(side="right", padx=(10, 0))
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=15, pady=10)

        self.carregar()

    def alternar_filtro(self):
        self.somente_nao_conformes = not self.somente_nao_conformes
        self.botao_filtro.configure(
            text="Mostrar todas" if self.somente_nao_conformes else "Mostrar só fora do padrão"
        )
        self.carregar()

    def carregar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(analises):
            for w in self.lista.winfo_children():
                w.destroy()
            if not analises:
                texto = "Nenhuma análise fora do padrão encontrada." if self.somente_nao_conformes else "Nenhuma análise registrada ainda."
                ctk.CTkLabel(self.lista, text=texto).pack(pady=20)
                return

            for a in analises:
                fora_do_padrao = a.get("conforme") is False
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#fef2f2" if fora_do_padrao else "#f0fdf4")
                linha.pack(fill="x", pady=4)

                data_hora = datetime.fromisoformat(a["coletado_em"]).strftime("%d/%m/%Y %H:%M")
                localidade_texto = LOCALIDADE_LABEL.get(a["localidade"], a["localidade"])
                status_texto = "⚠ Fora do padrão" if fora_do_padrao else "✓ Conforme"
                cor_status = "#dc2626" if fora_do_padrao else "#16a34a"

                cabecalho = ctk.CTkFrame(linha, fg_color="transparent")
                cabecalho.pack(fill="x", padx=10, pady=(8, 0))
                ctk.CTkLabel(
                    cabecalho, text=f"[{data_hora}] {localidade_texto}", font=ctk.CTkFont(weight="bold"), anchor="w"
                ).pack(side="left")
                ctk.CTkLabel(cabecalho, text=status_texto, text_color=cor_status, font=ctk.CTkFont(weight="bold")).pack(side="right")

                partes = []
                if a.get("turbidez_filtrada") is not None:
                    partes.append(f"Turb. filtrada: {a['turbidez_filtrada']}")
                if a.get("turbidez_tratada") is not None:
                    partes.append(f"Turb. tratada: {a['turbidez_tratada']}")
                if a.get("ph_tratada") is not None:
                    partes.append(f"pH tratada: {a['ph_tratada']}")
                if a.get("cloro_residual") is not None:
                    partes.append(f"Cloro residual: {a['cloro_residual']}")
                if a.get("cor_tratada") is not None:
                    partes.append(f"Cor tratada: {a['cor_tratada']}")
                ctk.CTkLabel(linha, text="  |  ".join(partes), anchor="w", font=ctk.CTkFont(size=12)).pack(
                    fill="x", padx=10, pady=(2, 5 if not fora_do_padrao else 2)
                )

                if fora_do_padrao and a.get("alertas"):
                    alertas = json.loads(a["alertas"])
                    ctk.CTkLabel(
                        linha, text="\n".join(f"• {alerta}" for alerta in alertas), anchor="w",
                        justify="left", text_color="#991b1b", font=ctk.CTkFont(size=12),
                    ).pack(fill="x", padx=10, pady=(0, 8))

        def erro(e):
            for w in self.lista.winfo_children():
                w.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar análises")

        rodar_em_background(self, lambda: self.api.listar_analises_eta(self.somente_nao_conformes), sucesso, erro)


class TelaEstoque(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api
        self.itens = []
        self.tecnicos = []

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Estoque", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")

        ctk.CTkButton(topo, text="+ Novo item", width=110, fg_color=COR_PRINCIPAL, command=self.abrir_novo_item).pack(
            side="right", padx=(10, 0)
        )
        ctk.CTkButton(topo, text="Movimentar", width=110, command=self.abrir_movimentar).pack(side="right", padx=10)
        ctk.CTkButton(topo, text="Manutenções ETA", width=130, command=self.abrir_manutencoes_eta).pack(side="right", padx=10)
        ctk.CTkButton(topo, text="Análises ETA", width=120, fg_color="#0369a1", command=self.abrir_analises_eta).pack(side="right", padx=10)
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def abrir_manutencoes_eta(self):
        JanelaManutencoesEta(self, self.api)

    def abrir_analises_eta(self):
        JanelaAnalisesEta(self, self.api)

    def abrir_novo_item(self):
        JanelaNovoItem(self, self.api, self.carregar)

    def abrir_movimentar(self):
        JanelaMovimentar(self, self.api, self.itens, self.tecnicos, self.carregar)

    def abrir_editar_item(self, item):
        JanelaEditarItem(self, self.api, item, self.carregar)

    def carregar(self):
        for widget in self.lista.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def buscar_dados():
            return self.api.listar_itens_estoque(), self.api.listar_tecnicos()

        def sucesso(resultado):
            itens, tecnicos = resultado
            self.itens = itens
            self.tecnicos = tecnicos
            for widget in self.lista.winfo_children():
                widget.destroy()

            if not itens:
                ctk.CTkLabel(self.lista, text="Nenhum item cadastrado ainda.").pack(pady=20)
                return

            cabecalho = ctk.CTkFrame(self.lista, fg_color="transparent")
            cabecalho.pack(fill="x", pady=(0, 5))
            for texto, largura in [("Item", 220), ("Saldo total", 100), ("Valor unit.", 90), ("Valor total", 100), ("Mínimo", 80)]:
                ctk.CTkLabel(cabecalho, text=texto, font=ctk.CTkFont(weight="bold"), width=largura, anchor="w").pack(
                    side="left", padx=5
                )

            valor_total_geral = 0
            for item in itens:
                abaixo_do_minimo = item["saldo_total"] < item["estoque_minimo"]
                linha = ctk.CTkFrame(
                    self.lista, fg_color="#fef2f2" if abaixo_do_minimo else "#f1f5f9", corner_radius=6, cursor="hand2"
                )
                linha.pack(fill="x", pady=2)
                linha.bind("<Button-1>", lambda e, it=item: self.abrir_editar_item(it))

                nome_exibido = f"⚠ {item['nome']}" if abaixo_do_minimo else item["nome"]
                widgets_linha = [
                    ctk.CTkLabel(linha, text=nome_exibido, width=220, anchor="w"),
                    ctk.CTkLabel(linha, text=f"{item['saldo_total']:.1f} {item['unidade_medida']}", width=100, anchor="w"),
                    ctk.CTkLabel(linha, text=f"R$ {item['valor_unitario']:.2f}", width=90, anchor="w"),
                    ctk.CTkLabel(linha, text=f"R$ {item['valor_total']:.2f}", width=100, anchor="w"),
                    ctk.CTkLabel(linha, text=f"{item['estoque_minimo']:.1f}", width=80, anchor="w"),
                ]
                for w in widgets_linha:
                    w.pack(side="left", padx=5, pady=8)
                    w.bind("<Button-1>", lambda e, it=item: self.abrir_editar_item(it))
                valor_total_geral += item["valor_total"]

            ctk.CTkLabel(
                self.lista, text=f"Valor total em estoque: R$ {valor_total_geral:.2f}",
                font=ctk.CTkFont(weight="bold", size=14),
            ).pack(anchor="w", pady=(15, 0))

        def erro(e):
            for widget in self.lista.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar estoque")

        rodar_em_background(self, buscar_dados, sucesso, erro)


class TelaSolicitacoes(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Solicitações de material", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def carregar(self):
        for widget in self.lista.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(solicitacoes):
            for widget in self.lista.winfo_children():
                widget.destroy()

            pendentes = [s for s in solicitacoes if s["status"] == "pendente"]
            aguardando_comprovante = [
                s for s in solicitacoes
                if s["status"] == "aprovada" and s.get("modo_aprovacao") == "compra_direta" and not s.get("nota_fiscal_foto")
            ]
            com_comprovante = [s for s in solicitacoes if s.get("nota_fiscal_foto")]

            if not pendentes and not aguardando_comprovante and not com_comprovante:
                ctk.CTkLabel(self.lista, text="Nenhuma solicitação pendente.").pack(pady=20)
                return

            if pendentes:
                ctk.CTkLabel(self.lista, text="Pendentes", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5, 5))
            for solicitacao in pendentes:
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)

                texto = f"Técnico #{solicitacao['tecnico_id']} pediu {solicitacao['quantidade']:.0f}x item #{solicitacao['item_id']}"
                if solicitacao.get("chamado_id"):
                    texto += f" (chamado #{solicitacao['chamado_id']})"
                ctk.CTkLabel(linha, text=texto, anchor="w").pack(fill="x", padx=10, pady=(10, 5))

                linha_botoes = ctk.CTkFrame(linha, fg_color="transparent")
                linha_botoes.pack(fill="x", padx=10, pady=(0, 10))
                ctk.CTkButton(
                    linha_botoes, text="Transferir do estoque", width=150, fg_color="#16a34a",
                    command=lambda s=solicitacao: self.aprovar(s, "estoque"),
                ).pack(side="left", padx=(0, 5))
                ctk.CTkButton(
                    linha_botoes, text="Autorizar compra direta", width=160, fg_color="#7c3aed",
                    command=lambda s=solicitacao: self.aprovar(s, "compra_direta"),
                ).pack(side="left", padx=5)
                ctk.CTkButton(
                    linha_botoes, text="Negar", width=90, fg_color="#dc2626",
                    command=lambda s=solicitacao: self.negar(s),
                ).pack(side="left", padx=5)

            if aguardando_comprovante:
                ctk.CTkLabel(
                    self.lista, text="Compra direta autorizada — aguardando o técnico enviar a nota fiscal",
                    font=ctk.CTkFont(weight="bold"),
                ).pack(anchor="w", pady=(15, 5))
            for solicitacao in aguardando_comprovante:
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#fef3c7")
                linha.pack(fill="x", pady=4)
                texto = f"Técnico #{solicitacao['tecnico_id']} — item #{solicitacao['item_id']} — autorizado, sem comprovante ainda"
                ctk.CTkLabel(linha, text=texto, anchor="w").pack(fill="x", padx=10, pady=10)

            if com_comprovante:
                ctk.CTkLabel(
                    self.lista, text="Compras diretas com nota fiscal enviada", font=ctk.CTkFont(weight="bold"),
                ).pack(anchor="w", pady=(15, 5))
            for solicitacao in com_comprovante:
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)
                texto = (
                    f"Técnico #{solicitacao['tecnico_id']} — item #{solicitacao['item_id']} — "
                    f"R$ {solicitacao['valor_compra']:.2f} — fornecedor #{solicitacao['fornecedor_id']}"
                )
                ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)
                ctk.CTkButton(
                    linha, text="Ver nota fiscal", width=110, fg_color="#6b7280", hover_color="#4b5563",
                    command=lambda s=solicitacao: self.ver_nota_fiscal(s),
                ).pack(side="right", padx=10)

        def erro(e):
            for widget in self.lista.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar solicitações")

        rodar_em_background(self, lambda: self.api.listar_solicitacoes(), sucesso, erro)

    def aprovar(self, solicitacao, modo):
        def fazer():
            return self.api.aprovar_solicitacao(solicitacao["id"], modo, "sede", "sede")

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao aprovar")

        rodar_em_background(self, fazer, lambda _: self.carregar(), erro)

    def ver_nota_fiscal(self, solicitacao):
        def buscar():
            return self.api.baixar_foto_leitura(solicitacao["nota_fiscal_foto"])

        def sucesso(conteudo):
            caminho = filedialog.asksaveasfilename(
                defaultextension=".jpg", initialfile=f"nota_fiscal_solicitacao_{solicitacao['id']}.jpg",
                filetypes=[("Imagem", "*.jpg")],
            )
            if not caminho:
                return
            with open(caminho, "wb") as f:
                f.write(conteudo)
            try:
                os.startfile(caminho)
            except Exception:
                messagebox.showinfo("Salvo", f"Nota fiscal salva em: {caminho}")

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao baixar nota fiscal")

        rodar_em_background(self, buscar, sucesso, erro)

    def negar(self, solicitacao):
        def fazer():
            return self.api.negar_solicitacao(solicitacao["id"])

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao negar")

        rodar_em_background(self, fazer, lambda _: self.carregar(), erro)


class JanelaNovoUsuarioLogin(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar):
        super().__init__(master)
        self.title("Cadastrar técnico/operador (com login)")
        self.geometry("380x460")
        self.api = api
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="Nome").pack(anchor="w", padx=20, pady=(20, 0))
        self.campo_nome = ctk.CTkEntry(self, width=320)
        self.campo_nome.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Telefone (vai ser o login dele)").pack(anchor="w", padx=20)
        self.campo_telefone = ctk.CTkEntry(self, width=320)
        self.campo_telefone.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Senha inicial").pack(anchor="w", padx=20)
        self.campo_senha = ctk.CTkEntry(self, width=320, show="*")
        self.campo_senha.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Tipo").pack(anchor="w", padx=20)
        self.combo_tipo = ctk.CTkOptionMenu(self, values=["tecnico", "quimico", "operador"], width=320)
        self.combo_tipo.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Localidade (obrigatório pra técnico; químico pode ficar em qualquer uma)").pack(anchor="w", padx=20)
        self.combo_localidade = ctk.CTkOptionMenu(self, values=[LOCALIDADE_LABEL[l] for l in LOCALIDADES], width=320)
        self.combo_localidade.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Cadastrar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        telefone = self.campo_telefone.get().strip()
        senha = self.campo_senha.get()
        if not nome or not telefone or not senha:
            messagebox.showwarning("Atenção", "Preencha nome, telefone e senha.")
            return

        localidade_valor = next(
            (k for k, v in LOCALIDADE_LABEL.items() if v == self.combo_localidade.get()), "sede"
        )

        self.botao_salvar.configure(state="disabled", text="Cadastrando...")

        def cadastrar():
            return self.api.cadastrar_usuario_login(nome, telefone, senha, self.combo_tipo.get(), localidade_valor)

        def sucesso(_):
            self.destroy()
            self.ao_salvar()
            messagebox.showinfo("Pronto", f"Cadastrado! Login: {telefone}")

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Cadastrar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao cadastrar")

        rodar_em_background(self, cadastrar, sucesso, erro)


class JanelaNovoFuncionario(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar):
        super().__init__(master)
        self.title("Novo funcionário")
        self.geometry("360x400")
        self.api = api
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="Nome").pack(anchor="w", padx=20, pady=(20, 0))
        self.campo_nome = ctk.CTkEntry(self, width=300)
        self.campo_nome.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Cargo").pack(anchor="w", padx=20)
        self.campo_cargo = ctk.CTkEntry(self, width=300)
        self.campo_cargo.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Telefone").pack(anchor="w", padx=20)
        self.campo_telefone = ctk.CTkEntry(self, width=300)
        self.campo_telefone.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Localidade").pack(anchor="w", padx=20)
        self.combo_localidade = ctk.CTkOptionMenu(self, values=[LOCALIDADE_LABEL[l] for l in LOCALIDADES], width=300)
        self.combo_localidade.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Cadastrar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do funcionário.")
            return

        localidade_valor = next(
            (k for k, v in LOCALIDADE_LABEL.items() if v == self.combo_localidade.get()), "sede"
        )

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def salvar_funcionario():
            return self.api.cadastrar_funcionario(
                nome, self.campo_cargo.get().strip(), self.campo_telefone.get().strip(), localidade_valor
            )

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Cadastrar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao cadastrar funcionário")

        rodar_em_background(self, salvar_funcionario, sucesso, erro)


class JanelaEditarFuncionario(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, funcionario, ao_salvar):
        super().__init__(master)
        self.title(f"Editar funcionário — {funcionario['nome']}")
        self.geometry("360x440")
        self.api = api
        self.funcionario = funcionario
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="Nome").pack(anchor="w", padx=20, pady=(20, 0))
        self.campo_nome = ctk.CTkEntry(self, width=300)
        self.campo_nome.insert(0, funcionario["nome"])
        self.campo_nome.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Cargo (mude aqui se ele trocar de função)").pack(anchor="w", padx=20)
        self.campo_cargo = ctk.CTkEntry(self, width=300)
        self.campo_cargo.insert(0, funcionario.get("cargo") or "")
        self.campo_cargo.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Telefone").pack(anchor="w", padx=20)
        self.campo_telefone = ctk.CTkEntry(self, width=300)
        self.campo_telefone.insert(0, funcionario.get("telefone") or "")
        self.campo_telefone.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Localidade").pack(anchor="w", padx=20)
        self.combo_localidade = ctk.CTkOptionMenu(self, values=[LOCALIDADE_LABEL[l] for l in LOCALIDADES], width=300)
        self.combo_localidade.set(LOCALIDADE_LABEL.get(funcionario.get("localidade"), LOCALIDADE_LABEL["sede"]))
        self.combo_localidade.pack(padx=20, pady=(0, 15))

        linha_botoes = ctk.CTkFrame(self, fg_color="transparent")
        linha_botoes.pack(padx=20, pady=10, fill="x")
        self.botao_salvar = ctk.CTkButton(linha_botoes, text="Salvar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(
            linha_botoes, text="Desativar", fg_color="#dc2626", hover_color="#991b1b", width=100,
            command=self.desativar,
        ).pack(side="right")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do funcionário.")
            return

        localidade_valor = next(
            (k for k, v in LOCALIDADE_LABEL.items() if v == self.combo_localidade.get()), "sede"
        )

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def atualizar():
            return self.api.atualizar_funcionario(
                self.funcionario["id"], nome, self.campo_cargo.get().strip(),
                self.campo_telefone.get().strip(), localidade_valor,
            )

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Salvar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao atualizar funcionário")

        rodar_em_background(self, atualizar, sucesso, erro)

    def desativar(self):
        if not messagebox.askyesno("Confirmar", f"Desativar o funcionário '{self.funcionario['nome']}'?"):
            return

        def fazer():
            return self.api.desativar_funcionario(self.funcionario["id"])

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao desativar funcionário")

        rodar_em_background(self, fazer, sucesso, erro)


class TelaFuncionarios(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Funcionários", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="+ Novo", width=90, fg_color=COR_PRINCIPAL, command=self.abrir_novo).pack(
            side="right", padx=(10, 0)
        )
        ctk.CTkButton(
            topo, text="+ Cadastrar login (técnico/operador)", width=230, fg_color="#7c3aed",
            command=self.abrir_novo_login,
        ).pack(side="right", padx=(10, 0))
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def abrir_novo(self):
        JanelaNovoFuncionario(self, self.api, self.carregar)

    def abrir_novo_login(self):
        JanelaNovoUsuarioLogin(self, self.api, self.carregar)

    def abrir_editar(self, funcionario):
        JanelaEditarFuncionario(self, self.api, funcionario, self.carregar)

    def carregar(self):
        for widget in self.lista.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(funcionarios):
            for widget in self.lista.winfo_children():
                widget.destroy()

            if not funcionarios:
                ctk.CTkLabel(self.lista, text="Nenhum funcionário cadastrado ainda.").pack(pady=20)
                return

            for f in funcionarios:
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#f1f5f9", cursor="hand2")
                linha.pack(fill="x", pady=4)
                localidade_texto = LOCALIDADE_LABEL.get(f.get("localidade"), "—")
                texto = f"{f['nome']} — {f.get('cargo') or '(sem cargo)'} — {localidade_texto} — {f.get('telefone') or '—'}"
                rotulo = ctk.CTkLabel(linha, text=texto, anchor="w", cursor="hand2")
                rotulo.pack(side="left", padx=10, pady=10, fill="x", expand=True)
                ctk.CTkLabel(linha, text="✏ editar", text_color="#0891b2", cursor="hand2").pack(side="right", padx=10)

                linha.bind("<Button-1>", lambda e, func=f: self.abrir_editar(func))
                rotulo.bind("<Button-1>", lambda e, func=f: self.abrir_editar(func))

        def erro(e):
            for widget in self.lista.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar funcionários")

        rodar_em_background(self, self.api.listar_funcionarios, sucesso, erro)


class JanelaNovoCliente(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar):
        super().__init__(master)
        self.title("Cadastrar cliente")
        self.geometry("380x560")
        self.api = api
        self.ao_salvar = ao_salvar

        campos = [
            ("Nome", "campo_nome"), ("Documento (CPF/CNPJ)", "campo_documento"),
            ("Endereço", "campo_endereco"), ("Bairro", "campo_bairro"),
            ("Cidade", "campo_cidade"), ("Hidrômetro", "campo_hidrometro"),
        ]
        for label, atributo in campos:
            ctk.CTkLabel(self, text=label).pack(anchor="w", padx=20, pady=(10, 0))
            entrada = ctk.CTkEntry(self, width=320)
            entrada.pack(padx=20, pady=(0, 5))
            setattr(self, atributo, entrada)

        ctk.CTkLabel(self, text="Categoria").pack(anchor="w", padx=20, pady=(10, 0))
        self.combo_categoria = ctk.CTkOptionMenu(self, values=["residencial", "comercial", "industrial"], width=320)
        self.combo_categoria.pack(padx=20, pady=(0, 5))

        ctk.CTkLabel(self, text="Localidade").pack(anchor="w", padx=20, pady=(10, 0))
        self.combo_localidade = ctk.CTkOptionMenu(self, values=[LOCALIDADE_LABEL[l] for l in LOCALIDADES], width=320)
        self.combo_localidade.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Cadastrar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do cliente.")
            return

        localidade_valor = next(
            (k for k, v in LOCALIDADE_LABEL.items() if v == self.combo_localidade.get()), "sede"
        )

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def cadastrar():
            return self.api.cadastrar_cliente(
                nome, self.campo_documento.get().strip(), self.campo_endereco.get().strip(),
                self.campo_bairro.get().strip(), self.campo_cidade.get().strip(),
                self.campo_hidrometro.get().strip(), self.combo_categoria.get(), localidade_valor,
            )

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Cadastrar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao cadastrar cliente")

        rodar_em_background(self, cadastrar, sucesso, erro)


class JanelaEditarCliente(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, cliente, ao_salvar):
        super().__init__(master)
        self.title(f"Editar cliente #{cliente['id']}")
        self.geometry("380x600")
        self.api = api
        self.cliente = cliente
        self.ao_salvar = ao_salvar

        campos = [
            ("Nome", "campo_nome", cliente.get("nome") or ""),
            ("Documento (CPF/CNPJ)", "campo_documento", cliente.get("documento") or ""),
            ("Endereço", "campo_endereco", cliente.get("endereco") or ""),
            ("Bairro", "campo_bairro", cliente.get("bairro") or ""),
            ("Cidade", "campo_cidade", cliente.get("cidade") or ""),
            ("Hidrômetro", "campo_hidrometro", cliente.get("hidrometro") or ""),
        ]
        for label, atributo, valor_atual in campos:
            ctk.CTkLabel(self, text=label).pack(anchor="w", padx=20, pady=(10, 0))
            entrada = ctk.CTkEntry(self, width=320)
            entrada.insert(0, valor_atual)
            entrada.pack(padx=20, pady=(0, 5))
            setattr(self, atributo, entrada)

        ctk.CTkLabel(self, text="Categoria").pack(anchor="w", padx=20, pady=(10, 0))
        self.combo_categoria = ctk.CTkOptionMenu(self, values=["residencial", "comercial", "industrial"], width=320)
        self.combo_categoria.set(cliente.get("categoria") or "residencial")
        self.combo_categoria.pack(padx=20, pady=(0, 5))

        ctk.CTkLabel(self, text="Localidade").pack(anchor="w", padx=20, pady=(10, 0))
        self.combo_localidade = ctk.CTkOptionMenu(self, values=[LOCALIDADE_LABEL[l] for l in LOCALIDADES], width=320)
        self.combo_localidade.set(LOCALIDADE_LABEL.get(cliente.get("localidade"), LOCALIDADE_LABEL["sede"]))
        self.combo_localidade.pack(padx=20, pady=(0, 15))

        linha_botoes = ctk.CTkFrame(self, fg_color="transparent")
        linha_botoes.pack(padx=20, pady=10, fill="x")
        self.botao_salvar = ctk.CTkButton(linha_botoes, text="Salvar alterações", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(side="left", expand=True, fill="x", padx=(0, 5))
        ctk.CTkButton(
            linha_botoes, text="Desativar", fg_color="#dc2626", hover_color="#991b1b", width=100,
            command=self.desativar,
        ).pack(side="right")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do cliente.")
            return

        localidade_valor = next(
            (k for k, v in LOCALIDADE_LABEL.items() if v == self.combo_localidade.get()), "sede"
        )

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def atualizar():
            return self.api.atualizar_cliente(
                self.cliente["id"], nome, self.campo_documento.get().strip(), self.campo_endereco.get().strip(),
                self.campo_bairro.get().strip(), self.campo_cidade.get().strip(),
                self.campo_hidrometro.get().strip(), self.combo_categoria.get(), localidade_valor,
            )

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Salvar alterações")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao atualizar cliente")

        rodar_em_background(self, atualizar, sucesso, erro)

    def desativar(self):
        if not messagebox.askyesno(
            "Confirmar", f"Desativar o cadastro de '{self.cliente['nome']}'? "
            "Ele some da lista, mas o histórico de chamados dele continua intacto."
        ):
            return

        def fazer():
            return self.api.desativar_cliente(self.cliente["id"])

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao desativar cliente")

        rodar_em_background(self, fazer, sucesso, erro)


class TelaClientes(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Clientes", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="+ Novo cliente", width=130, fg_color=COR_PRINCIPAL, command=self.abrir_novo).pack(
            side="right", padx=(10, 0)
        )
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def abrir_novo(self):
        JanelaNovoCliente(self, self.api, self.carregar)

    def abrir_editar(self, cliente):
        JanelaEditarCliente(self, self.api, cliente, self.carregar)

    def aprovar(self, cliente):
        def fazer():
            return self.api.aprovar_cliente(cliente["id"])

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao aprovar cliente")

        rodar_em_background(self, fazer, lambda _: self.carregar(), erro)

    def carregar(self):
        for widget in self.lista.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(clientes):
            for widget in self.lista.winfo_children():
                widget.destroy()

            if not clientes:
                ctk.CTkLabel(self.lista, text="Nenhum cliente cadastrado ainda.").pack(pady=20)
                return

            for c in clientes:
                pendente = c.get("status_cadastro") == "pendente"
                linha = ctk.CTkFrame(
                    self.lista, corner_radius=8, fg_color="#fef3c7" if pendente else "#f1f5f9", cursor="hand2"
                )
                linha.pack(fill="x", pady=4)
                localidade_texto = LOCALIDADE_LABEL.get(c.get("localidade"), "—")
                status_texto = " — ⏳ PENDENTE DE APROVAÇÃO" if pendente else ""
                texto = f"#{c['id']} {c['nome']} — {c.get('endereco') or '—'} — {localidade_texto}{status_texto}"
                rotulo = ctk.CTkLabel(linha, text=texto, anchor="w", cursor="hand2")
                rotulo.pack(side="left", padx=10, pady=10, fill="x", expand=True)

                if pendente:
                    ctk.CTkButton(
                        linha, text="Aprovar", width=90, fg_color="#16a34a",
                        command=lambda cli=c: self.aprovar(cli),
                    ).pack(side="right", padx=(5, 10))
                else:
                    ctk.CTkLabel(linha, text="✏ editar", text_color="#0891b2", cursor="hand2").pack(side="right", padx=10)

                linha.bind("<Button-1>", lambda e, cli=c: self.abrir_editar(cli))
                rotulo.bind("<Button-1>", lambda e, cli=c: self.abrir_editar(cli))

        def erro(e):
            for widget in self.lista.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar clientes")

        rodar_em_background(self, self.api.listar_clientes, sucesso, erro)


class TelaLeituras(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Leituras de hidrômetro", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def carregar(self):
        for widget in self.lista.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(leituras):
            for widget in self.lista.winfo_children():
                widget.destroy()

            pendentes = [l for l in leituras if l["status"] == "pendente"]
            if not pendentes:
                ctk.CTkLabel(self.lista, text="Nenhuma leitura pendente de validação.").pack(pady=20)
                return

            for leitura in pendentes:
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)

                texto = f"Cliente #{leitura['cliente_id']} — {leitura['competencia']} — informou: {leitura['valor_informado']:.0f}"
                if leitura.get("valor_ocr") is not None:
                    ok = "✓ confere" if leitura.get("ocr_confere") else "⚠ NÃO confere com a foto (OCR)"
                    texto += f"  |  OCR leu: {leitura['valor_ocr']:.0f} ({ok})"
                else:
                    texto += "  |  (sem OCR — confira a foto manualmente)"

                ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)

                ctk.CTkButton(
                    linha, text="Ver foto", width=80, fg_color="#6b7280", hover_color="#4b5563",
                    command=lambda l=leitura: self.ver_foto(l),
                ).pack(side="left", padx=5)
                ctk.CTkButton(
                    linha, text="Aprovar", width=90, fg_color="#16a34a",
                    command=lambda l=leitura: self.aprovar(l),
                ).pack(side="left", padx=5)
                ctk.CTkButton(
                    linha, text="Rejeitar", width=90, fg_color="#dc2626", hover_color="#991b1b",
                    command=lambda l=leitura: self.rejeitar(l),
                ).pack(side="left", padx=(5, 10))

        def erro(e):
            for widget in self.lista.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar leituras")

        rodar_em_background(self, lambda: self.api.listar_leituras(), sucesso, erro)

    def ver_foto(self, leitura):
        def buscar():
            return self.api.baixar_foto_leitura(leitura["foto_caminho"])

        def sucesso(conteudo):
            caminho = filedialog.asksaveasfilename(
                defaultextension=".jpg", initialfile=f"leitura_{leitura['id']}.jpg", filetypes=[("Imagem", "*.jpg")],
            )
            if not caminho:
                return
            with open(caminho, "wb") as f:
                f.write(conteudo)
            try:
                os.startfile(caminho)
            except Exception:
                messagebox.showinfo("Salvo", f"Foto salva em: {caminho}")

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao baixar foto")

        rodar_em_background(self, buscar, sucesso, erro)

    def aprovar(self, leitura):
        def fazer():
            return self.api.aprovar_leitura(leitura["id"])

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao aprovar")

        rodar_em_background(self, fazer, lambda _: self.carregar(), erro)

    def rejeitar(self, leitura):
        motivo = simpledialog.askstring("Rejeitar leitura", "Motivo da rejeição (o cliente vai ver isso):")
        if not motivo:
            return

        def fazer():
            return self.api.rejeitar_leitura(leitura["id"], motivo)

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao rejeitar")

        rodar_em_background(self, fazer, lambda _: self.carregar(), erro)


class JanelaTarifa(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar, faixa=None):
        super().__init__(master)
        self.title("Editar faixa de tarifa" if faixa else "Nova faixa de tarifa")
        self.geometry("360x420")
        self.api = api
        self.faixa = faixa
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="Consumo mínimo (m³)").pack(anchor="w", padx=20, pady=(20, 0))
        self.campo_min = ctk.CTkEntry(self, width=300)
        self.campo_min.insert(0, str(faixa["consumo_min"]) if faixa else "0")
        self.campo_min.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Consumo máximo (m³) — deixe vazio se for a última faixa").pack(anchor="w", padx=20)
        self.campo_max = ctk.CTkEntry(self, width=300)
        if faixa and faixa.get("consumo_max") is not None:
            self.campo_max.insert(0, str(faixa["consumo_max"]))
        self.campo_max.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Valor por m³ (R$)").pack(anchor="w", padx=20)
        self.campo_valor = ctk.CTkEntry(self, width=300)
        self.campo_valor.insert(0, str(faixa["valor_m3"]) if faixa else "3.50")
        self.campo_valor.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="% de esgoto sobre o valor da água").pack(anchor="w", padx=20)
        self.campo_esgoto = ctk.CTkEntry(self, width=300)
        self.campo_esgoto.insert(0, str(faixa["percentual_esgoto"]) if faixa else "80")
        self.campo_esgoto.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Salvar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        try:
            minimo = float(self.campo_min.get().replace(",", "."))
            maximo = float(self.campo_max.get().replace(",", ".")) if self.campo_max.get().strip() else None
            valor = float(self.campo_valor.get().replace(",", "."))
            esgoto = float(self.campo_esgoto.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Atenção", "Os campos numéricos precisam ser números válidos.")
            return

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def salvar_tarifa():
            if self.faixa:
                return self.api.atualizar_tarifa(self.faixa["id"], minimo, maximo, valor, esgoto)
            return self.api.criar_tarifa(minimo, maximo, valor, esgoto)

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Salvar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao salvar tarifa")

        rodar_em_background(self, salvar_tarifa, sucesso, erro)


class TelaFaturamento(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Faturamento", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="Atualizar", width=90, command=self.carregar).pack(side="right")

        # --- Seção de tarifas ---
        secao_tarifas = ctk.CTkFrame(self, fg_color="transparent")
        secao_tarifas.pack(fill="x", padx=20, pady=(0, 10))
        cabecalho_tarifas = ctk.CTkFrame(secao_tarifas, fg_color="transparent")
        cabecalho_tarifas.pack(fill="x")
        ctk.CTkLabel(cabecalho_tarifas, text="Tarifas por faixa de consumo", font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkButton(
            cabecalho_tarifas, text="+ Nova faixa", width=110, fg_color=COR_PRINCIPAL, command=self.abrir_nova_tarifa
        ).pack(side="right")
        self.lista_tarifas = ctk.CTkFrame(secao_tarifas, fg_color="transparent")
        self.lista_tarifas.pack(fill="x", pady=(5, 0))

        ctk.CTkLabel(self, text="Faturas em aberto", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=20, pady=(10, 0))
        self.lista_faturas = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista_faturas.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def abrir_nova_tarifa(self):
        JanelaTarifa(self, self.api, self.carregar)

    def abrir_editar_tarifa(self, faixa):
        JanelaTarifa(self, self.api, self.carregar, faixa=faixa)

    def carregar(self):
        for widget in self.lista_tarifas.winfo_children():
            widget.destroy()
        for widget in self.lista_faturas.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.lista_faturas, text="Carregando...").pack(pady=20)

        def buscar_dados():
            return self.api.listar_tarifas(), self.api.listar_faturas(status="aberto")

        def sucesso(resultado):
            tarifas, faturas = resultado

            for widget in self.lista_tarifas.winfo_children():
                widget.destroy()
            if not tarifas:
                ctk.CTkLabel(self.lista_tarifas, text="Nenhuma tarifa cadastrada.").pack(anchor="w")
            for faixa in tarifas:
                maximo_texto = f"{faixa['consumo_max']:.0f}" if faixa.get("consumo_max") is not None else "∞"
                texto = (
                    f"{faixa['consumo_min']:.0f} a {maximo_texto} m³  →  R$ {faixa['valor_m3']:.2f}/m³  "
                    f"(esgoto: {faixa['percentual_esgoto']:.0f}%)"
                )
                linha = ctk.CTkFrame(self.lista_tarifas, fg_color="#f1f5f9", corner_radius=6, cursor="hand2")
                linha.pack(fill="x", pady=2)
                rotulo = ctk.CTkLabel(linha, text=texto, anchor="w", cursor="hand2")
                rotulo.pack(side="left", padx=10, pady=6, fill="x", expand=True)
                linha.bind("<Button-1>", lambda e, f=faixa: self.abrir_editar_tarifa(f))
                rotulo.bind("<Button-1>", lambda e, f=faixa: self.abrir_editar_tarifa(f))

            for widget in self.lista_faturas.winfo_children():
                widget.destroy()
            if not faturas:
                ctk.CTkLabel(self.lista_faturas, text="Nenhuma fatura em aberto.").pack(pady=20)
                return

            for fatura in faturas:
                linha = ctk.CTkFrame(self.lista_faturas, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)
                texto = (
                    f"Cliente #{fatura['cliente_id']} — {fatura['competencia']} — "
                    f"consumo {fatura['consumo_m3']:.0f}m³ — R$ {fatura['valor_total']:.2f}"
                )
                ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)

                ctk.CTkButton(
                    linha, text="📄 PDF", width=70, fg_color="#6b7280", hover_color="#4b5563",
                    command=lambda f=fatura: self.baixar_pdf(f),
                ).pack(side="left", padx=5)
                ctk.CTkButton(
                    linha, text="Marcar paga", width=100, fg_color="#16a34a",
                    command=lambda f=fatura: self.marcar_paga(f),
                ).pack(side="left", padx=(5, 10))

        def erro(e):
            for widget in self.lista_faturas.winfo_children():
                widget.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar faturamento")

        rodar_em_background(self, buscar_dados, sucesso, erro)

    def marcar_paga(self, fatura):
        def fazer():
            return self.api.marcar_fatura_paga(fatura["id"])

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao marcar como paga")

        rodar_em_background(self, fazer, lambda _: self.carregar(), erro)

    def baixar_pdf(self, fatura):
        def buscar():
            return self.api.baixar_fatura_pdf(fatura["id"])

        def sucesso(pdf_bytes):
            caminho = filedialog.asksaveasfilename(
                defaultextension=".pdf", initialfile=f"fatura_{fatura['id']}.pdf", filetypes=[("PDF", "*.pdf")],
            )
            if not caminho:
                return
            with open(caminho, "wb") as f:
                f.write(pdf_bytes)
            try:
                os.startfile(caminho)
            except Exception:
                messagebox.showinfo("Salvo", f"PDF salvo em: {caminho}")

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao gerar PDF")

        rodar_em_background(self, buscar, sucesso, erro)


class JanelaFornecedor(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar, fornecedor=None):
        super().__init__(master)
        self.title("Editar fornecedor" if fornecedor else "Novo fornecedor")
        self.geometry("380x460")
        self.api = api
        self.fornecedor = fornecedor
        self.ao_salvar = ao_salvar

        campos = [
            ("Nome / Razão social", "campo_nome", fornecedor.get("nome") if fornecedor else ""),
            ("CNPJ/CPF", "campo_documento", fornecedor.get("documento") if fornecedor else ""),
            ("Telefone", "campo_telefone", fornecedor.get("telefone") if fornecedor else ""),
            ("E-mail", "campo_email", fornecedor.get("email") if fornecedor else ""),
            ("Endereço", "campo_endereco", fornecedor.get("endereco") if fornecedor else ""),
        ]
        for label, atributo, valor_atual in campos:
            ctk.CTkLabel(self, text=label).pack(anchor="w", padx=20, pady=(10, 0))
            entrada = ctk.CTkEntry(self, width=320)
            entrada.insert(0, valor_atual or "")
            entrada.pack(padx=20, pady=(0, 5))
            setattr(self, atributo, entrada)

        linha_botoes = ctk.CTkFrame(self, fg_color="transparent")
        linha_botoes.pack(padx=20, pady=15, fill="x")
        self.botao_salvar = ctk.CTkButton(linha_botoes, text="Salvar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(side="left", expand=True, fill="x", padx=(0, 5))
        if fornecedor:
            ctk.CTkButton(
                linha_botoes, text="Desativar", fg_color="#dc2626", hover_color="#991b1b", width=100,
                command=self.desativar,
            ).pack(side="right")

    def salvar(self):
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Atenção", "Digite o nome do fornecedor.")
            return

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def salvar_fornecedor():
            args = (nome, self.campo_documento.get().strip(), self.campo_telefone.get().strip(),
                     self.campo_email.get().strip(), self.campo_endereco.get().strip())
            if self.fornecedor:
                return self.api.atualizar_fornecedor(self.fornecedor["id"], *args)
            return self.api.cadastrar_fornecedor(*args)

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Salvar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao salvar fornecedor")

        rodar_em_background(self, salvar_fornecedor, sucesso, erro)

    def desativar(self):
        if not messagebox.askyesno("Confirmar", f"Desativar o fornecedor '{self.fornecedor['nome']}'?"):
            return

        def fazer():
            return self.api.desativar_fornecedor(self.fornecedor["id"])

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao desativar fornecedor")

        rodar_em_background(self, fazer, sucesso, erro)


class JanelaContaPagar(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, fornecedores, ao_salvar):
        super().__init__(master)
        self.title("Nova conta a pagar")
        self.geometry("380x420")
        self.api = api
        self.fornecedores = fornecedores
        self.ao_salvar = ao_salvar

        nomes = ["(sem fornecedor específico)"] + [f["nome"] for f in fornecedores]
        ctk.CTkLabel(self, text="Fornecedor").pack(anchor="w", padx=20, pady=(20, 0))
        self.combo_fornecedor = ctk.CTkOptionMenu(self, values=nomes, width=320)
        self.combo_fornecedor.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Descrição").pack(anchor="w", padx=20)
        self.campo_descricao = ctk.CTkEntry(self, width=320)
        self.campo_descricao.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Valor (R$)").pack(anchor="w", padx=20)
        self.campo_valor = ctk.CTkEntry(self, width=320)
        self.campo_valor.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Vencimento (DD/MM/AAAA)").pack(anchor="w", padx=20)
        self.campo_vencimento = ctk.CTkEntry(self, width=320)
        self.campo_vencimento.insert(0, (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y"))
        self.campo_vencimento.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Cadastrar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        descricao = self.campo_descricao.get().strip()
        if not descricao:
            messagebox.showwarning("Atenção", "Digite a descrição.")
            return
        try:
            valor = float(self.campo_valor.get().replace(",", "."))
            vencimento = datetime.strptime(self.campo_vencimento.get().strip(), "%d/%m/%Y")
        except ValueError:
            messagebox.showwarning("Atenção", "Confira o valor e a data de vencimento (DD/MM/AAAA).")
            return

        nome_escolhido = self.combo_fornecedor.get()
        fornecedor = next((f for f in self.fornecedores if f["nome"] == nome_escolhido), None)

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def criar():
            return self.api.criar_conta_pagar(
                fornecedor["id"] if fornecedor else None, descricao, valor, vencimento.isoformat()
            )

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Cadastrar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao criar conta")

        rodar_em_background(self, criar, sucesso, erro)


class JanelaContaReceber(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar):
        super().__init__(master)
        self.title("Nova conta a receber")
        self.geometry("380x400")
        self.api = api
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="ID do cliente (deixe vazio se não for de um cliente específico)").pack(
            anchor="w", padx=20, pady=(20, 0)
        )
        self.campo_cliente_id = ctk.CTkEntry(self, width=320)
        self.campo_cliente_id.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Descrição (ex: Taxa de religação)").pack(anchor="w", padx=20)
        self.campo_descricao = ctk.CTkEntry(self, width=320)
        self.campo_descricao.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Valor (R$)").pack(anchor="w", padx=20)
        self.campo_valor = ctk.CTkEntry(self, width=320)
        self.campo_valor.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Vencimento (DD/MM/AAAA)").pack(anchor="w", padx=20)
        self.campo_vencimento = ctk.CTkEntry(self, width=320)
        self.campo_vencimento.insert(0, (datetime.now() + timedelta(days=10)).strftime("%d/%m/%Y"))
        self.campo_vencimento.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Cadastrar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        descricao = self.campo_descricao.get().strip()
        if not descricao:
            messagebox.showwarning("Atenção", "Digite a descrição.")
            return
        try:
            valor = float(self.campo_valor.get().replace(",", "."))
            vencimento = datetime.strptime(self.campo_vencimento.get().strip(), "%d/%m/%Y")
        except ValueError:
            messagebox.showwarning("Atenção", "Confira o valor e a data de vencimento (DD/MM/AAAA).")
            return

        texto_cliente_id = self.campo_cliente_id.get().strip()
        cliente_id = int(texto_cliente_id) if texto_cliente_id.isdigit() else None

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def criar():
            return self.api.criar_conta_receber(cliente_id, descricao, valor, vencimento.isoformat())

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Cadastrar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao criar conta")

        rodar_em_background(self, criar, sucesso, erro)


class TelaFinanceiro(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api
        self.fornecedores = []

        abas = ctk.CTkTabview(self)
        abas.pack(fill="both", expand=True, padx=20, pady=20)
        abas.add("Resumo")
        abas.add("Empresa")
        abas.add("Fornecedores")
        abas.add("Contas a pagar")
        abas.add("Contas a receber")

        self._montar_resumo(abas.tab("Resumo"))
        self._montar_empresa(abas.tab("Empresa"))
        self._montar_fornecedores(abas.tab("Fornecedores"))
        self._montar_contas_pagar(abas.tab("Contas a pagar"))
        self._montar_contas_receber(abas.tab("Contas a receber"))

    # --- Resumo ---
    def _montar_resumo(self, container):
        self.frame_resumo = ctk.CTkFrame(container, fg_color="transparent")
        self.frame_resumo.pack(fill="both", expand=True)
        ctk.CTkButton(container, text="Atualizar", width=90, command=self._carregar_resumo).pack(anchor="e", pady=(0, 10))
        self._carregar_resumo()

    def _carregar_resumo(self):
        for w in self.frame_resumo.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.frame_resumo, text="Carregando...").pack(pady=20)

        def sucesso(resumo):
            for w in self.frame_resumo.winfo_children():
                w.destroy()

            linha = ctk.CTkFrame(self.frame_resumo, fg_color="transparent")
            linha.pack(fill="x", pady=10)

            def card(pai, titulo, valor, cor):
                c = ctk.CTkFrame(pai, fg_color=cor, corner_radius=10)
                ctk.CTkLabel(c, text=titulo, text_color="white", font=ctk.CTkFont(size=13)).pack(pady=(15, 0))
                ctk.CTkLabel(
                    c, text=f"R$ {valor:.2f}", text_color="white", font=ctk.CTkFont(size=22, weight="bold")
                ).pack(pady=(0, 15))
                return c

            card(linha, "Total a pagar", resumo["total_a_pagar"], "#dc2626").pack(side="left", expand=True, fill="both", padx=5)
            card(linha, "Total a receber", resumo["total_a_receber"], "#16a34a").pack(side="left", expand=True, fill="both", padx=5)
            cor_saldo = "#16a34a" if resumo["saldo_projetado"] >= 0 else "#dc2626"
            card(linha, "Saldo projetado", resumo["saldo_projetado"], cor_saldo).pack(side="left", expand=True, fill="both", padx=5)

            ctk.CTkLabel(
                self.frame_resumo,
                text=f"(sendo R$ {resumo['total_a_receber_faturas_agua']:.2f} de faturas de água/esgoto "
                     f"e R$ {resumo['total_a_receber_outras']:.2f} de outras cobranças)",
                font=ctk.CTkFont(size=12), text_color="gray",
            ).pack(pady=10)

        def erro(e):
            for w in self.frame_resumo.winfo_children():
                w.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar resumo")

        rodar_em_background(self, self.api.resumo_financeiro, sucesso, erro)

    # --- Empresa ---
    def _montar_empresa(self, container):
        ctk.CTkLabel(container, text="Dados da empresa/prefeitura (aparece no sistema e nos documentos)",
                     font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(10, 15))

        campos = [
            ("Nome fantasia", "campo_nome_fantasia"),
            ("Razão social", "campo_razao_social"),
            ("CNPJ", "campo_cnpj"),
            ("Endereço", "campo_endereco_empresa"),
            ("Telefone", "campo_telefone_empresa"),
            ("E-mail", "campo_email_empresa"),
        ]
        for label, atributo in campos:
            ctk.CTkLabel(container, text=label).pack(anchor="w")
            entrada = ctk.CTkEntry(container, width=400)
            entrada.pack(anchor="w", pady=(0, 10))
            setattr(self, atributo, entrada)

        self.botao_salvar_empresa = ctk.CTkButton(
            container, text="Salvar dados da empresa", fg_color=COR_PRINCIPAL, command=self._salvar_empresa
        )
        self.botao_salvar_empresa.pack(anchor="w", pady=10)

        self._carregar_empresa()

    def _carregar_empresa(self):
        def sucesso(empresa):
            self.campo_nome_fantasia.delete(0, "end")
            self.campo_nome_fantasia.insert(0, empresa.get("nome_fantasia") or "")
            self.campo_razao_social.delete(0, "end")
            self.campo_razao_social.insert(0, empresa.get("razao_social") or "")
            self.campo_cnpj.delete(0, "end")
            self.campo_cnpj.insert(0, empresa.get("cnpj") or "")
            self.campo_endereco_empresa.delete(0, "end")
            self.campo_endereco_empresa.insert(0, empresa.get("endereco") or "")
            self.campo_telefone_empresa.delete(0, "end")
            self.campo_telefone_empresa.insert(0, empresa.get("telefone") or "")
            self.campo_email_empresa.delete(0, "end")
            self.campo_email_empresa.insert(0, empresa.get("email") or "")

        def erro(e):
            pass  # tela de cadastro em branco tá ok se ainda não tinha nada

        rodar_em_background(self, self.api.obter_empresa, sucesso, erro)

    def _salvar_empresa(self):
        self.botao_salvar_empresa.configure(state="disabled", text="Salvando...")

        def salvar():
            return self.api.atualizar_empresa(
                self.campo_nome_fantasia.get().strip(), self.campo_razao_social.get().strip(),
                self.campo_cnpj.get().strip(), self.campo_endereco_empresa.get().strip(),
                self.campo_telefone_empresa.get().strip(), self.campo_email_empresa.get().strip(),
            )

        def sucesso(_):
            self.botao_salvar_empresa.configure(state="normal", text="Salvar dados da empresa")
            messagebox.showinfo("Pronto", "Dados da empresa atualizados!")

        def erro(e):
            self.botao_salvar_empresa.configure(state="normal", text="Salvar dados da empresa")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao salvar")

        rodar_em_background(self, salvar, sucesso, erro)

    # --- Fornecedores ---
    def _montar_fornecedores(self, container):
        topo = ctk.CTkFrame(container, fg_color="transparent")
        topo.pack(fill="x", pady=(10, 10))
        ctk.CTkButton(topo, text="+ Novo fornecedor", fg_color=COR_PRINCIPAL, command=self._abrir_novo_fornecedor).pack(side="right", padx=(10, 0))
        ctk.CTkButton(topo, text="Atualizar", command=self._carregar_fornecedores).pack(side="right")

        self.lista_fornecedores = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self.lista_fornecedores.pack(fill="both", expand=True)
        self._carregar_fornecedores()

    def _abrir_novo_fornecedor(self):
        JanelaFornecedor(self, self.api, self._carregar_fornecedores)

    def _abrir_editar_fornecedor(self, fornecedor):
        JanelaFornecedor(self, self.api, self._carregar_fornecedores, fornecedor=fornecedor)

    def _carregar_fornecedores(self):
        for w in self.lista_fornecedores.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista_fornecedores, text="Carregando...").pack(pady=20)

        def sucesso(fornecedores):
            self.fornecedores = fornecedores
            for w in self.lista_fornecedores.winfo_children():
                w.destroy()
            if not fornecedores:
                ctk.CTkLabel(self.lista_fornecedores, text="Nenhum fornecedor cadastrado ainda.").pack(pady=20)
                return
            for f in fornecedores:
                linha = ctk.CTkFrame(self.lista_fornecedores, corner_radius=8, fg_color="#f1f5f9", cursor="hand2")
                linha.pack(fill="x", pady=4)
                texto = f"{f['nome']} — {f.get('documento') or '—'} — {f.get('telefone') or '—'}"
                rotulo = ctk.CTkLabel(linha, text=texto, anchor="w", cursor="hand2")
                rotulo.pack(side="left", padx=10, pady=10, fill="x", expand=True)
                linha.bind("<Button-1>", lambda e, ff=f: self._abrir_editar_fornecedor(ff))
                rotulo.bind("<Button-1>", lambda e, ff=f: self._abrir_editar_fornecedor(ff))

        def erro(e):
            for w in self.lista_fornecedores.winfo_children():
                w.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar fornecedores")

        rodar_em_background(self, self.api.listar_fornecedores, sucesso, erro)

    # --- Contas a pagar ---
    def _montar_contas_pagar(self, container):
        topo = ctk.CTkFrame(container, fg_color="transparent")
        topo.pack(fill="x", pady=(10, 10))
        ctk.CTkButton(topo, text="+ Nova conta", fg_color=COR_PRINCIPAL, command=self._abrir_nova_conta_pagar).pack(side="right", padx=(10, 0))
        ctk.CTkButton(topo, text="Atualizar", command=self._carregar_contas_pagar).pack(side="right")

        self.lista_contas_pagar = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self.lista_contas_pagar.pack(fill="both", expand=True)
        self._carregar_contas_pagar()

    def _abrir_nova_conta_pagar(self):
        def apos_carregar_fornecedores(fornecedores):
            JanelaContaPagar(self, self.api, fornecedores, self._carregar_contas_pagar)

        rodar_em_background(self, self.api.listar_fornecedores, apos_carregar_fornecedores, lambda e: apos_carregar_fornecedores([]))

    def _carregar_contas_pagar(self):
        for w in self.lista_contas_pagar.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista_contas_pagar, text="Carregando...").pack(pady=20)

        def sucesso(contas):
            for w in self.lista_contas_pagar.winfo_children():
                w.destroy()
            abertas = [c for c in contas if c["status"] == "aberto"]
            if not abertas:
                ctk.CTkLabel(self.lista_contas_pagar, text="Nenhuma conta a pagar em aberto.").pack(pady=20)
                return
            for c in abertas:
                linha = ctk.CTkFrame(self.lista_contas_pagar, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)
                venc = datetime.fromisoformat(c["vencimento"]).strftime("%d/%m/%Y")
                texto = f"{c['descricao']} — R$ {c['valor']:.2f} — vence {venc}"
                ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)
                ctk.CTkButton(
                    linha, text="Marcar paga", width=100, fg_color="#16a34a",
                    command=lambda cc=c: self._marcar_paga_pagar(cc),
                ).pack(side="right", padx=10)

        def erro(e):
            for w in self.lista_contas_pagar.winfo_children():
                w.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar contas")

        rodar_em_background(self, lambda: self.api.listar_contas_pagar(), sucesso, erro)

    def _marcar_paga_pagar(self, conta):
        def fazer():
            return self.api.marcar_conta_pagar_paga(conta["id"])

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao marcar como paga")

        rodar_em_background(self, fazer, lambda _: self._carregar_contas_pagar(), erro)

    # --- Contas a receber (outras) ---
    def _montar_contas_receber(self, container):
        ctk.CTkLabel(
            container, text="Cobranças fora do faturamento de água (taxas, multas etc). "
                            "As faturas de água/esgoto ficam na aba Faturamento.",
            font=ctk.CTkFont(size=12), text_color="gray",
        ).pack(anchor="w", pady=(10, 5))

        topo = ctk.CTkFrame(container, fg_color="transparent")
        topo.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(topo, text="+ Nova cobrança", fg_color=COR_PRINCIPAL, command=self._abrir_nova_conta_receber).pack(side="right", padx=(10, 0))
        ctk.CTkButton(topo, text="Atualizar", command=self._carregar_contas_receber).pack(side="right")

        self.lista_contas_receber = ctk.CTkScrollableFrame(container, fg_color="transparent")
        self.lista_contas_receber.pack(fill="both", expand=True)
        self._carregar_contas_receber()

    def _abrir_nova_conta_receber(self):
        JanelaContaReceber(self, self.api, self._carregar_contas_receber)

    def _carregar_contas_receber(self):
        for w in self.lista_contas_receber.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista_contas_receber, text="Carregando...").pack(pady=20)

        def sucesso(contas):
            for w in self.lista_contas_receber.winfo_children():
                w.destroy()
            abertas = [c for c in contas if c["status"] == "aberto"]
            if not abertas:
                ctk.CTkLabel(self.lista_contas_receber, text="Nenhuma cobrança avulsa em aberto.").pack(pady=20)
                return
            for c in abertas:
                linha = ctk.CTkFrame(self.lista_contas_receber, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)
                venc = datetime.fromisoformat(c["vencimento"]).strftime("%d/%m/%Y")
                cliente_texto = f"cliente #{c['cliente_id']}" if c.get("cliente_id") else "sem cliente"
                texto = f"{c['descricao']} ({cliente_texto}) — R$ {c['valor']:.2f} — vence {venc}"
                ctk.CTkLabel(linha, text=texto, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)
                ctk.CTkButton(
                    linha, text="Marcar paga", width=100, fg_color="#16a34a",
                    command=lambda cc=c: self._marcar_paga_receber(cc),
                ).pack(side="right", padx=10)

        def erro(e):
            for w in self.lista_contas_receber.winfo_children():
                w.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar cobranças")

        rodar_em_background(self, lambda: self.api.listar_contas_receber(), sucesso, erro)

    def _marcar_paga_receber(self, conta):
        def fazer():
            return self.api.marcar_conta_receber_paga(conta["id"])

        def erro(e):
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao marcar como paga")

        rodar_em_background(self, fazer, lambda _: self._carregar_contas_receber(), erro)


MODALIDADE_LABEL = {
    "pregao_eletronico": "Pregão Eletrônico",
    "pregao_presencial": "Pregão Presencial",
    "concorrencia": "Concorrência",
    "tomada_precos": "Tomada de Preços",
    "convite": "Convite",
    "dispensa": "Dispensa de Licitação",
    "inexigibilidade": "Inexigibilidade",
}

STATUS_LICITACAO_LABEL = {
    "rascunho": "Rascunho",
    "publicada": "Publicada",
    "em_analise": "Em análise",
    "homologada": "Homologada",
    "fracassada": "Fracassada",
    "cancelada": "Cancelada",
}

STATUS_LICITACAO_COR = {
    "rascunho": "#9ca3af",
    "publicada": "#0891b2",
    "em_analise": "#d97706",
    "homologada": "#16a34a",
    "fracassada": "#dc2626",
    "cancelada": "#6b7280",
}

PROXIMOS_STATUS = {
    "rascunho": ["publicada", "cancelada"],
    "publicada": ["em_analise", "cancelada"],
    "em_analise": ["homologada", "fracassada", "cancelada"],
    "homologada": [],
    "fracassada": [],
    "cancelada": [],
}


class JanelaLicitacao(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, ao_salvar, licitacao=None):
        super().__init__(master)
        self.title("Editar licitação" if licitacao else "Nova licitação")
        self.geometry("420x560")
        self.api = api
        self.licitacao = licitacao
        self.ao_salvar = ao_salvar

        ctk.CTkLabel(self, text="Número do processo (opcional)").pack(anchor="w", padx=20, pady=(20, 0))
        self.campo_numero = ctk.CTkEntry(self, width=360)
        self.campo_numero.insert(0, (licitacao or {}).get("numero_processo") or "")
        self.campo_numero.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Modalidade").pack(anchor="w", padx=20)
        valores_modalidade = list(MODALIDADE_LABEL.values())
        self.combo_modalidade = ctk.CTkOptionMenu(self, values=valores_modalidade, width=360)
        if licitacao:
            self.combo_modalidade.set(MODALIDADE_LABEL.get(licitacao["modalidade"], valores_modalidade[0]))
        self.combo_modalidade.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Objeto (o que está sendo licitado)").pack(anchor="w", padx=20)
        self.campo_objeto = ctk.CTkEntry(self, width=360)
        self.campo_objeto.insert(0, (licitacao or {}).get("objeto") or "")
        self.campo_objeto.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Valor estimado (R$)").pack(anchor="w", padx=20)
        self.campo_valor = ctk.CTkEntry(self, width=360)
        self.campo_valor.insert(0, str((licitacao or {}).get("valor_estimado") or ""))
        self.campo_valor.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Data de abertura (DD/MM/AAAA)").pack(anchor="w", padx=20)
        self.campo_data = ctk.CTkEntry(self, width=360)
        if licitacao:
            self.campo_data.insert(0, datetime.fromisoformat(licitacao["data_abertura"]).strftime("%d/%m/%Y"))
        else:
            self.campo_data.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.campo_data.pack(padx=20, pady=(0, 10))

        ctk.CTkLabel(self, text="Observações (opcional)").pack(anchor="w", padx=20)
        self.campo_observacoes = ctk.CTkEntry(self, width=360)
        self.campo_observacoes.insert(0, (licitacao or {}).get("observacoes") or "")
        self.campo_observacoes.pack(padx=20, pady=(0, 15))

        self.botao_salvar = ctk.CTkButton(self, text="Salvar", fg_color=COR_PRINCIPAL, command=self.salvar)
        self.botao_salvar.pack(padx=20, pady=10, fill="x")

    def salvar(self):
        objeto = self.campo_objeto.get().strip()
        if not objeto:
            messagebox.showwarning("Atenção", "Descreva o objeto da licitação.")
            return
        try:
            valor = float(self.campo_valor.get().replace(",", ".")) if self.campo_valor.get().strip() else None
            data_abertura = datetime.strptime(self.campo_data.get().strip(), "%d/%m/%Y")
        except ValueError:
            messagebox.showwarning("Atenção", "Confira o valor e a data de abertura (DD/MM/AAAA).")
            return

        modalidade_valor = next(
            (k for k, v in MODALIDADE_LABEL.items() if v == self.combo_modalidade.get()), "pregao_eletronico"
        )

        self.botao_salvar.configure(state="disabled", text="Salvando...")

        def salvar_licitacao():
            args = (self.campo_numero.get().strip() or None, modalidade_valor, objeto, valor,
                     data_abertura.isoformat(), self.campo_observacoes.get().strip() or None)
            if self.licitacao:
                return self.api.atualizar_licitacao(self.licitacao["id"], *args)
            return self.api.criar_licitacao(*args)

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_salvar.configure(state="normal", text="Salvar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao salvar licitação")

        rodar_em_background(self, salvar_licitacao, sucesso, erro)


class JanelaMudarStatusLicitacao(ctk.CTkToplevel):
    def __init__(self, master, api: ApiClient, licitacao, ao_salvar):
        super().__init__(master)
        self.title(f"Mudar status — Licitação #{licitacao['id']}")
        self.geometry("380x420")
        self.api = api
        self.licitacao = licitacao
        self.ao_salvar = ao_salvar

        proximos = PROXIMOS_STATUS.get(licitacao["status"], [])
        ctk.CTkLabel(
            self, text=f"Status atual: {STATUS_LICITACAO_LABEL.get(licitacao['status'], licitacao['status'])}",
            font=ctk.CTkFont(weight="bold"),
        ).pack(anchor="w", padx=20, pady=(20, 10))

        if not proximos:
            ctk.CTkLabel(self, text="Esse status é final — não dá mais pra mudar.").pack(padx=20, pady=20)
            return

        ctk.CTkLabel(self, text="Novo status").pack(anchor="w", padx=20)
        self.combo_status = ctk.CTkOptionMenu(
            self, values=[STATUS_LICITACAO_LABEL[s] for s in proximos], width=320,
            command=self._ao_trocar_status,
        )
        self.combo_status.pack(padx=20, pady=(0, 10))

        # Campos extras, só aparecem/importam quando o novo status é "Homologada"
        self.label_vencedor = ctk.CTkLabel(self, text="Vencedor")
        self.campo_vencedor = ctk.CTkEntry(self, width=320)
        self.label_valor_final = ctk.CTkLabel(self, text="Valor final (R$)")
        self.campo_valor_final = ctk.CTkEntry(self, width=320)

        self.botao_confirmar = ctk.CTkButton(self, text="Confirmar", fg_color=COR_PRINCIPAL, command=self.confirmar)
        self.botao_confirmar.pack(padx=20, pady=20, fill="x", side="bottom")

        self._ao_trocar_status(self.combo_status.get())

    def _ao_trocar_status(self, valor_escolhido):
        status_valor = next((k for k, v in STATUS_LICITACAO_LABEL.items() if v == valor_escolhido), None)
        if status_valor == "homologada":
            self.label_vencedor.pack(anchor="w", padx=20)
            self.campo_vencedor.pack(padx=20, pady=(0, 10))
            self.label_valor_final.pack(anchor="w", padx=20)
            self.campo_valor_final.pack(padx=20, pady=(0, 10))
        else:
            self.label_vencedor.pack_forget()
            self.campo_vencedor.pack_forget()
            self.label_valor_final.pack_forget()
            self.campo_valor_final.pack_forget()

    def confirmar(self):
        status_valor = next(
            (k for k, v in STATUS_LICITACAO_LABEL.items() if v == self.combo_status.get()), None
        )
        vencedor = None
        valor_final = None
        if status_valor == "homologada":
            vencedor = self.campo_vencedor.get().strip()
            if not vencedor:
                messagebox.showwarning("Atenção", "Informe o vencedor pra homologar.")
                return
            try:
                valor_final = float(self.campo_valor_final.get().replace(",", ".")) if self.campo_valor_final.get().strip() else None
            except ValueError:
                messagebox.showwarning("Atenção", "Valor final precisa ser um número.")
                return

        self.botao_confirmar.configure(state="disabled", text="Confirmando...")

        def fazer():
            return self.api.mudar_status_licitacao(self.licitacao["id"], status_valor, vencedor, None, valor_final)

        def sucesso(_):
            self.destroy()
            self.ao_salvar()

        def erro(e):
            self.botao_confirmar.configure(state="normal", text="Confirmar")
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao mudar status")

        rodar_em_background(self, fazer, sucesso, erro)


class TelaLicitacoes(ctk.CTkFrame):
    def __init__(self, master, api: ApiClient):
        super().__init__(master, fg_color="transparent")
        self.api = api

        topo = ctk.CTkFrame(self, fg_color="transparent")
        topo.pack(fill="x", padx=20, pady=(20, 10))
        ctk.CTkLabel(topo, text="Licitações", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left")
        ctk.CTkButton(topo, text="+ Nova licitação", fg_color=COR_PRINCIPAL, command=self.abrir_nova).pack(side="right", padx=(10, 0))
        ctk.CTkButton(topo, text="Atualizar", command=self.carregar).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=20, pady=10)

        self.carregar()

    def abrir_nova(self):
        JanelaLicitacao(self, self.api, self.carregar)

    def abrir_editar(self, licitacao):
        JanelaLicitacao(self, self.api, self.carregar, licitacao=licitacao)

    def abrir_mudar_status(self, licitacao):
        JanelaMudarStatusLicitacao(self, self.api, licitacao, self.carregar)

    def carregar(self):
        for w in self.lista.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.lista, text="Carregando...").pack(pady=20)

        def sucesso(licitacoes):
            for w in self.lista.winfo_children():
                w.destroy()
            if not licitacoes:
                ctk.CTkLabel(self.lista, text="Nenhuma licitação cadastrada ainda.").pack(pady=20)
                return
            for lic in licitacoes:
                linha = ctk.CTkFrame(self.lista, corner_radius=8, fg_color="#f1f5f9")
                linha.pack(fill="x", pady=4)

                cor_status = STATUS_LICITACAO_COR.get(lic["status"], "#6b7280")
                cabecalho = ctk.CTkFrame(linha, fg_color="transparent")
                cabecalho.pack(fill="x", padx=10, pady=(8, 0))
                numero_texto = f"#{lic['numero_processo']} — " if lic.get("numero_processo") else ""
                ctk.CTkLabel(
                    cabecalho, text=f"{numero_texto}{MODALIDADE_LABEL.get(lic['modalidade'], lic['modalidade'])}",
                    font=ctk.CTkFont(weight="bold"), anchor="w",
                ).pack(side="left")
                ctk.CTkLabel(
                    cabecalho, text=STATUS_LICITACAO_LABEL.get(lic["status"], lic["status"]),
                    text_color=cor_status, font=ctk.CTkFont(weight="bold"),
                ).pack(side="right")

                ctk.CTkLabel(linha, text=lic["objeto"], anchor="w", justify="left").pack(fill="x", padx=10, pady=(2, 0))

                valor_texto = f"Estimado: R$ {lic['valor_estimado']:.2f}" if lic.get("valor_estimado") else ""
                if lic.get("status") == "homologada" and lic.get("vencedor"):
                    valor_texto += f"  |  Vencedor: {lic['vencedor']}"
                    if lic.get("valor_final"):
                        valor_texto += f" (R$ {lic['valor_final']:.2f})"
                ctk.CTkLabel(linha, text=valor_texto, anchor="w", font=ctk.CTkFont(size=12), text_color="gray").pack(
                    fill="x", padx=10, pady=(2, 8)
                )

                linha_botoes = ctk.CTkFrame(linha, fg_color="transparent")
                linha_botoes.pack(fill="x", padx=10, pady=(0, 8))
                ctk.CTkButton(
                    linha_botoes, text="Editar", width=80, fg_color="#6b7280", hover_color="#4b5563",
                    command=lambda l=lic: self.abrir_editar(l),
                ).pack(side="left", padx=(0, 5))
                if PROXIMOS_STATUS.get(lic["status"]):
                    ctk.CTkButton(
                        linha_botoes, text="Mudar status", width=110, fg_color=COR_PRINCIPAL,
                        command=lambda l=lic: self.abrir_mudar_status(l),
                    ).pack(side="left")

        def erro(e):
            for w in self.lista.winfo_children():
                w.destroy()
            messagebox.showerror("Erro", str(e) if isinstance(e, ApiError) else "Falha ao carregar licitações")

        rodar_em_background(self, lambda: self.api.listar_licitacoes(), sucesso, erro)


class Aplicativo(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SIGA — Água e Esgoto — Painel do Operador")
        self.geometry("1000x650")

        self.api = ApiClient()
        self.tela_splash = TelaSplash(self, self.ao_terminar_splash)
        self.tela_splash.pack(fill="both", expand=True)

    def ao_terminar_splash(self):
        self.tela_splash.pack_forget()
        self.tela_login = TelaLogin(self, self.api, self.ao_logar)
        self.tela_login.pack(fill="both", expand=True)

    def ao_logar(self):
        self.tela_login.pack_forget()
        self.montar_painel()

    def montar_painel(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        barra_lateral = ctk.CTkFrame(self, width=180, fg_color=COR_PRINCIPAL, corner_radius=0)
        barra_lateral.grid(row=0, column=0, sticky="ns")
        barra_lateral.grid_propagate(False)

        ctk.CTkLabel(
            barra_lateral, text="💧 SIGA\nÁgua e Esgoto", font=ctk.CTkFont(size=16, weight="bold"), text_color="white"
        ).pack(pady=30)

        self.conteudo = ctk.CTkFrame(self, fg_color="white")
        self.conteudo.grid(row=0, column=1, sticky="nsew")

        ctk.CTkButton(
            barra_lateral, text="Dashboard", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_dashboard,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Chamados", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_chamados,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Clientes", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_clientes,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Estoque", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_estoque,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Leituras", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_leituras,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Faturamento", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_faturamento,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Financeiro", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_financeiro,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Licitações", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_licitacoes,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Solicitações", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_solicitacoes,
        ).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(
            barra_lateral, text="Funcionários", fg_color="transparent", hover_color="#0e7490",
            command=self.mostrar_funcionarios,
        ).pack(fill="x", padx=10, pady=5)

        self.mostrar_dashboard()

    def _limpar_conteudo(self):
        for widget in self.conteudo.winfo_children():
            widget.destroy()

    def mostrar_dashboard(self):
        self._limpar_conteudo()
        TelaDashboard(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_chamados(self):
        self._limpar_conteudo()
        TelaChamados(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_clientes(self):
        self._limpar_conteudo()
        TelaClientes(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_estoque(self):
        self._limpar_conteudo()
        TelaEstoque(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_leituras(self):
        self._limpar_conteudo()
        TelaLeituras(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_faturamento(self):
        self._limpar_conteudo()
        TelaFaturamento(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_financeiro(self):
        self._limpar_conteudo()
        TelaFinanceiro(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_licitacoes(self):
        self._limpar_conteudo()
        TelaLicitacoes(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_solicitacoes(self):
        self._limpar_conteudo()
        TelaSolicitacoes(self.conteudo, self.api).pack(fill="both", expand=True)

    def mostrar_funcionarios(self):
        self._limpar_conteudo()
        TelaFuncionarios(self.conteudo, self.api).pack(fill="both", expand=True)


if __name__ == "__main__":
    app = Aplicativo()
    app.mainloop()
