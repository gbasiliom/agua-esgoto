"""Acompanhamento ao vivo do técnico (sem tela): detecta chamado novo atribuído e resposta às solicitações de material.
O app consulta o servidor a cada 15 s (veja TecnicoApp.iniciar_ao_vivo) e esta classe diz o que mudou."""

INTERVALO_S = 15
ABERTOS = ("atribuido", "em_andamento")
TIPO_LABEL = {"vazamento": "Vazamento", "manutencao": "Manutenção", "religacao": "Religação", "vistoria": "Vistoria", "outro": "Outro"}
LOCAL_LABEL = {"sede": "Chalé (sede)", "penha_do_coco": "Penha do Coco", "bananal": "Bananal", "agua_limpa": "Água Limpa"}


def texto_chamado_novo(c):
    local = LOCAL_LABEL.get(c.get("local_atendimento"))
    return (f"Novo chamado #{c['id']}: {TIPO_LABEL.get(c['tipo'], c['tipo'])} ({c['prioridade']})"
            + (f" — {local}" if local else ""))


def texto_solicitacao(s):
    if s["status"] == "negada":
        return f"Solicitação #{s['id']} NEGADA" + (f": {s['observacao']}" if s.get("observacao") else "")
    if s.get("modo_aprovacao") == "compra_direta":
        return f"Solicitação #{s['id']} aprovada: compra direta autorizada — envie a nota fiscal."
    return f"Solicitação #{s['id']} aprovada: material transferido para o seu estoque."


class EstadoTecnico:
    def __init__(self):
        self.chamados_vistos = None      # ids já conhecidos (None = primeira consulta, não avisa)
        self.solicitacoes = {}           # id -> status
        self._primeira_solic = True
        self.abertos = 0

    def receber(self, chamados, solicitacoes=None):
        """-> {'chamados_novos': [...], 'solicitacoes': [...] , 'avisos': [textos]}"""
        novos = []
        ids = {c["id"] for c in chamados}
        if self.chamados_vistos is not None:
            novos = [c for c in chamados if c["id"] not in self.chamados_vistos and c["status"] == "atribuido"]
        self.chamados_vistos = (self.chamados_vistos or set()) | ids
        self.abertos = sum(1 for c in chamados if c["status"] in ABERTOS)

        decididas = []
        if solicitacoes is not None:
            if not self._primeira_solic:
                decididas = [s for s in solicitacoes
                             if self.solicitacoes.get(s["id"]) == "pendente" and s["status"] != "pendente"]
            self.solicitacoes = {s["id"]: s["status"] for s in solicitacoes}
            self._primeira_solic = False
        return {
            "chamados_novos": novos,
            "solicitacoes": decididas,
            "avisos": [texto_chamado_novo(c) for c in novos] + [texto_solicitacao(s) for s in decididas],
        }

    def texto_cartao_chamados(self):
        if not self.abertos:
            return "Atendimentos atribuídos a você"
        return f"{self.abertos} atendimento(s) aguardando você" if self.abertos > 1 else "1 atendimento aguardando você"
