"""Tema visual SIGA / SAAE Chalé — azul-marinho institucional sobre fundo branco.

TROCAR AQUI (um único lugar) quando o tom exato do site do SAAE for conferido.
O brasão oficial de Chalé NÃO vem no projeto: coloque o arquivo fornecido pela
Prefeitura/SAAE em assets/brasao.png (PNG com fundo transparente). Enquanto o
arquivo não existir, o app mostra só o nome — nada quebra.
"""
import os

# RGBA 0–1 (formato do Kivy)
AZUL_MARINHO = (0.043, 0.165, 0.357, 1)      # #0B2A5B  topo e botões principais
AZUL_ESCURO = (0.027, 0.106, 0.231, 1)       # #071B3B  texto sobre branco / variações
AZUL_CLARO = (0.91, 0.94, 0.98, 1)           # #E8F0FA  faixas e cartões sutis
BRANCO = (1, 1, 1, 1)
CINZA_TEXTO = (0.28, 0.33, 0.40, 1)
CINZA_LINHA = (0.82, 0.85, 0.89, 1)
# Semântica (aviso/erro/ok) — fora da identidade, só para estado
VERDE_OK = (0.03, 0.46, 0.28, 1)
AMBAR = (0.71, 0.45, 0.03, 1)
VERMELHO = (0.71, 0.14, 0.09, 1)


def caminho_brasao(pasta_app):
    """Retorna o caminho do brasão se o arquivo existir; senão string vazia."""
    p = os.path.join(pasta_app, "assets", "brasao.png")
    return p if os.path.exists(p) else ""
