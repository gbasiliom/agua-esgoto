"""Conferência LOCAL dos limites (Portaria GM/MS 888/2021), para o operador ver o alerta
na hora, mesmo sem internet. Espelha backend/routers/analise_eta_router.avaliar_conformidade;
o servidor continua sendo a fonte oficial e recalcula ao receber."""


def avaliar(d):
    alertas = []
    tf, tt = d.get("turbidez_filtrada"), d.get("turbidez_tratada")
    if tf is not None and tf > 1.0:
        alertas.append(f"Turbidez filtrada {tf:g} NTU acima do máximo de 1,0 NTU")
    elif tf is not None and tf > 0.5:
        alertas.append(f"Turbidez filtrada {tf:g} NTU acima da meta de 0,5 NTU (atenção)")
    if tt is not None and tt > 5.0:
        alertas.append(f"Turbidez tratada {tt:g} NTU acima do máximo de 5,0 NTU")
    ph = d.get("ph_tratada")
    if ph is not None and not (6.0 <= ph <= 9.5):
        alertas.append(f"pH tratada {ph:g} fora da faixa 6,0–9,5")
    cl = d.get("cloro_residual")
    if cl is not None and not (0.2 <= cl <= 5.0):
        alertas.append(f"Cloro residual {cl:g} mg/L fora da faixa 0,2–5,0 mg/L")
    cor = d.get("cor_tratada")
    if cor is not None and cor > 15:
        alertas.append(f"Cor tratada {cor:g} UC acima do máximo de 15 UC")
    return alertas


def plausivel(d):
    """Erros de digitação óbvios (bloqueiam o envio). Retorna lista de mensagens."""
    erros = []
    for campo, rotulo in (("ph_bruta", "pH da água bruta"), ("ph_tratada", "pH da água tratada")):
        v = d.get(campo)
        if v is not None and not (0 <= v <= 14):
            erros.append(f"{rotulo} deve estar entre 0 e 14.")
    for campo, rotulo in (("vazao_ls", "Vazão"), ("turbidez_bruta", "Turbidez bruta"), ("turbidez_filtrada", "Turbidez filtrada"),
                          ("turbidez_tratada", "Turbidez tratada"), ("sulfato_dosagem", "Dosagem de sulfato"),
                          ("cloro_dosagem", "Dosagem de cloro"), ("cloro_residual", "Cloro residual"),
                          ("cor_bruta", "Cor bruta"), ("cor_tratada", "Cor tratada")):
        v = d.get(campo)
        if v is not None and v < 0:
            erros.append(f"{rotulo} não pode ser negativa.")
    return erros
