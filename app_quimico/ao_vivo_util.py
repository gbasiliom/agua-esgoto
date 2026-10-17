"""Regras do acompanhamento ao vivo (sem tela): textos, alertas e estado recebido do servidor.
Mesma lógica do painel Windows (painel_windows/ao_vivo.py)."""
import json
from datetime import datetime

LOCALIDADE_LABEL = {"sede": "Chalé (sede)", "penha_do_coco": "Penha do Coco", "bananal": "Bananal", "agua_limpa": "Água Limpa"}
INTERVALO_S = 15
MAX_EVENTOS = 40
CAMPOS = [("turbidez_filtrada", "Turb. filtrada"), ("turbidez_tratada", "Turb. tratada"), ("ph_tratada", "pH"),
          ("cloro_residual", "Cloro"), ("cor_tratada", "Cor")]


def duracao_texto(minutos):
    if minutos is None:
        return "—"
    return f"{minutos // 60}h{minutos % 60:02d}" if minutos >= 60 else f"{minutos} min"


def hora_br(texto_iso):
    try:
        return datetime.fromisoformat(texto_iso).strftime("%H:%M")
    except (TypeError, ValueError):
        return "—"


def lista_alertas(texto):
    if not texto:
        return []
    try:
        v = json.loads(texto)
        return v if isinstance(v, list) else [str(v)]
    except ValueError:
        return [texto]


def alertas_de(localidades):
    """-> [(chave, texto)]. A chave só muda quando surge um problema novo (evita repetir o aviso a cada consulta)."""
    saida = []
    for l in localidades:
        nome = LOCALIDADE_LABEL.get(l["localidade"], l["localidade"])
        if l.get("ultima_conforme") is False:
            motivo = (l.get("ultimos_alertas") or ["parâmetro fora do padrão"])[0]
            saida.append((f"fora:{l['localidade']}:{l['ultima_coleta']}",
                          f"{nome}: análise das {hora_br(l['ultima_coleta'])} fora do padrão — {motivo}"))
        if l.get("atrasada"):
            saida.append((f"atraso:{l['localidade']}:{l.get('ultima_coleta')}",
                          f"{nome}: sem análise há {duracao_texto(l['minutos_desde_ultima'])} "
                          f"(atrasada em {duracao_texto(l['minutos_atraso'])})"))
    return saida


def situacao_texto(l):
    """-> (rótulo, nível) com nível em 'ok' | 'erro' | 'atraso' | 'vazio'."""
    if not l["tem_dados"]:
        return "Sem dados", "vazio"
    if l["ultima_conforme"] is False:
        return "FORA DO PADRÃO", "erro"
    if l["atrasada"]:
        return "ANÁLISE ATRASADA", "atraso"
    return "Conforme", "ok"


def linha_analise(a):
    """-> (texto, texto_secundario) de uma análise para a lista."""
    nome = LOCALIDADE_LABEL.get(a["localidade"], a["localidade"])
    fora = a.get("conforme") is False
    partes = [f"{rot} {a[k]}" for k, rot in CAMPOS if a.get(k) is not None]
    sec = "; ".join(lista_alertas(a.get("alertas"))) if fora else (" · ".join(partes) or "—")
    return f"{nome} · {hora_br(a['coletado_em'])} · " + ("FORA DO PADRÃO" if fora else "Conforme"), sec


def linha_lavagem(l):
    nome = LOCALIDADE_LABEL.get(l["localidade"], l["localidade"])
    det = []
    if l.get("tempo_gasto_min") is not None:
        det.append(f"{l['tempo_gasto_min']:g} min")
    if l.get("volume_gasto") is not None:
        det.append(f"volume {l['volume_gasto']:g}")
    return f"{nome} · {hora_br(l['hora'])} · Lavagem de filtro", " · ".join(det) or "—"


class EstadoAoVivo:
    """Guarda o que já foi recebido e entrega só as mudanças."""

    def __init__(self):
        self.ids = [0, 0]
        self.eventos = []          # dicts {tipo, dados}
        self.localidades = []
        self.alertas = []          # [(chave, texto)]
        self._vistos = None        # None = primeira consulta (não avisa)

    def receber(self, dados):
        """-> lista de textos de alertas NOVOS (para avisar o químico)."""
        self.ids = [dados["ultimo_id_analise"], dados["ultimo_id_lavagem"]]
        novos = [{"tipo": "analise", "dados": a} for a in dados["analises"]]
        novos += [{"tipo": "lavagem", "dados": l} for l in dados["lavagens"]]
        self.eventos = (novos + self.eventos)
        self.eventos.sort(key=lambda e: e["dados"].get("coletado_em") or e["dados"].get("hora") or "", reverse=True)
        self.eventos = self.eventos[:MAX_EVENTOS]
        self.localidades = dados["localidades"]
        self.alertas = alertas_de(self.localidades)
        chaves = {c for c, _ in self.alertas}
        novos_alertas = [] if self._vistos is None else [t for c, t in self.alertas if c not in self._vistos]
        self._vistos = chaves
        return novos_alertas
