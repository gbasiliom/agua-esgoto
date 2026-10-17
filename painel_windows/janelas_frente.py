"""Janelas secundárias SEMPRE na frente.

No Windows, o CTkToplevel do CustomTkinter costuma abrir ATRÁS da janela principal. Este módulo corrige isso de uma
vez para todas as janelas do painel (Novo item, Novo cliente, Análises da ETA, Resultado, Laudo etc.):

1. toda CTkToplevel vira "filha" da janela que a abriu (transient) — o Windows mantém a filha sempre acima da mãe;
2. ao abrir, a janela é trazida para a frente e recebe o foco (com um "topmost" rápido para furar o bloqueio do Windows);
3. caixas de aviso (messagebox) e de escolher arquivo (filedialog) abrem presas à janela que está em uso — assim
   aparecem na frente dela e não atrás.

Uso: `import janelas_frente; janelas_frente.instalar()` uma vez, antes de criar qualquer janela (main.py e main_quimico.py).
"""
import functools
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

_FUNCOES_AVISO = ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel", "askquestion",
                  "askretrycancel", "askyesnocancel")
_FUNCOES_PERGUNTA = ("askstring", "askinteger", "askfloat")
_FUNCOES_ARQUIVO = ("asksaveasfilename", "askopenfilename", "askopenfilenames", "askdirectory", "asksaveasfile",
                    "askopenfile")


def trazer_para_frente(janela, foco=True):
    """Traz a janela para a frente. `foco=False` só levanta (não tira o foco de um campo já selecionado)."""
    try:
        if not janela.winfo_exists():
            return
        if janela.state() == "iconic":
            janela.deiconify()
        janela.lift()
        if foco:
            janela.attributes("-topmost", True)
            janela.focus_force()
            janela.after(400, lambda: _soltar_topmost(janela))
    except tk.TclError:
        pass


def _soltar_topmost(janela):
    try:
        if janela.winfo_exists():
            janela.attributes("-topmost", False)
    except tk.TclError:
        pass


def janela_ativa():
    """Janela (principal ou secundária) que está com o foco agora; None se não der para saber."""
    try:
        raiz = tk._default_root
        if raiz is None:
            return None
        w = raiz.focus_get()
        return w.winfo_toplevel() if w is not None else raiz
    except Exception:
        return None


def _com_pai_padrao(funcao):
    @functools.wraps(funcao)
    def embrulho(*args, **kwargs):
        if kwargs.get("parent") is None:
            pai = janela_ativa()
            if pai is not None:
                kwargs["parent"] = pai
        return funcao(*args, **kwargs)
    embrulho._siga_frente = True
    return embrulho


def instalar():
    """Idempotente: pode ser chamada mais de uma vez."""
    original = ctk.CTkToplevel.__init__
    if not getattr(original, "_siga_frente", False):
        def novo_init(self, *args, **kwargs):
            original(self, *args, **kwargs)
            pai = args[0] if args else kwargs.get("master")
            try:
                raiz = pai.winfo_toplevel() if pai is not None else None
                if raiz is not None and raiz is not self:
                    self.transient(raiz)
            except tk.TclError:
                pass
            # depois que a janela terminou de ser montada (e o CustomTkinter terminou o que faz ao abrir)
            self.after(30, lambda: trazer_para_frente(self, foco=True))
            self.after(300, lambda: trazer_para_frente(self, foco=False))
            self.after(700, lambda: trazer_para_frente(self, foco=False))
        novo_init._siga_frente = True
        novo_init.__wrapped__ = original
        ctk.CTkToplevel.__init__ = novo_init

    for modulo, nomes in ((messagebox, _FUNCOES_AVISO), (filedialog, _FUNCOES_ARQUIVO), (simpledialog, _FUNCOES_PERGUNTA)):
        for nome in nomes:
            f = getattr(modulo, nome, None)
            if f is not None and not getattr(f, "_siga_frente", False):
                setattr(modulo, nome, _com_pai_padrao(f))
