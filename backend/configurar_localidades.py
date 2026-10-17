"""Configura as 4 localidades do SAAE Chalé (população abastecida, manancial, filtração)
e gera o plano de amostragem da Portaria GM/MS 888/2021. Pode rodar de novo à vontade:
atualiza a configuração e regera só as regras automáticas (as editadas à mão são mantidas).

Uso (com o backend rodando):
    python configurar_localidades.py http://localhost:8000 <login-admin>
A senha é pedida no terminal (não é gravada em lugar nenhum).

POPULAÇÃO ABASTECIDA — valores informados em 14/10/2026, CONFIRMAR e ajustar abaixo:
  Bananal        500 domicílios x 1,8 hab/dom = 900
  Penha do Coco  260 domicílios x 1,8 hab/dom = 468
  Água Limpa     ~300 moradores, mas a maioria mora na roça com mina própria (solução individual):
                 o número realmente ATENDIDO pela ETA é menor -> use nº de ligações do SAAE x 1,8
  Sede           = área urbana de Chalé. Valor 4.407 é só um TETO (total de Chalé no IBGE 2022, 6.075,
                 menos Bananal, Penha do Coco e Água Limpa). A população urbana real é menor: troque
                 pelo nº de ligações ativas da sede x moradores por domicílio (ou pelo urbano do IBGE).
Qualquer valor abaixo de 5.000 hab. mantém o mínimo de rede em 5 amostras/mês.
"""
import getpass
import sys

import requests

LOCALIDADES = {
    "sede":          {"populacao_abastecida": 4407, "manancial": "superficial", "filtracao": "lenta", "numero_filtros": 1},
    "penha_do_coco": {"populacao_abastecida": 468,  "manancial": "superficial", "filtracao": "lenta", "numero_filtros": 1},
    "bananal":       {"populacao_abastecida": 900,  "manancial": "superficial", "filtracao": "lenta", "numero_filtros": 1},
    "agua_limpa":    {"populacao_abastecida": 300,  "manancial": "superficial", "filtracao": "lenta", "numero_filtros": 1},
}
# Ajuste numero_filtros para a quantidade real de filtros lentos de cada ETA.


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    url, login = sys.argv[1].rstrip("/"), sys.argv[2]
    r = requests.post(f"{url}/auth/login", json={"identificador": login, "senha": getpass.getpass("Senha do admin: ")}, timeout=15)
    if r.status_code != 200:
        sys.exit(f"Login recusado: {r.json().get('detail')}")
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    for loc, cfg in LOCALIDADES.items():
        a = requests.put(f"{url}/qualidade/config/{loc}", json=cfg, headers=h, timeout=15)
        if a.status_code != 200:
            sys.exit(f"{loc}: {a.json().get('detail')}")
        g = requests.post(f"{url}/qualidade/regras/gerar/{loc}", headers=h, timeout=15)
        if g.status_code != 200:
            sys.exit(f"{loc}: {g.json().get('detail')}")
        rede = next((x for x in g.json()["regras"] if x["grupo"] == "bact_rede"), None)
        print(f"{loc:14} pop {cfg['populacao_abastecida']:>5} -> {len(g.json()['regras'])} regras; rede: {rede['quantidade'] if rede else '-'}/{rede['periodo'] if rede else ''}")
        for aviso in g.json()["avisos"]:
            print("   aviso:", aviso)


if __name__ == "__main__":
    main()
