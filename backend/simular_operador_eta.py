"""Simula o operador da ETA lançando análises, para testar o acompanhamento ao vivo do químico sem o celular.

Uso (dentro da pasta backend, com o servidor rodando):
    python simular_operador_eta.py TELEFONE SENHA conforme
    python simular_operador_eta.py TELEFONE SENHA fora        (turbidez/pH/cloro fora da Portaria 888)
    python simular_operador_eta.py TELEFONE SENHA lavagem
Opcional: --url http://192.168.0.115:8000  (padrão http://127.0.0.1:8000)
TELEFONE/SENHA = login de um usuário do tipo operador_eta (crie no painel: Gestão > Funcionários > Cadastrar login).
Os dados entram de verdade no banco — use só em teste."""
import sys
from datetime import datetime, timedelta, timezone

import requests

args = [a for a in sys.argv[1:] if not a.startswith("--")]
url = "http://127.0.0.1:8000"
if "--url" in sys.argv:
    url = sys.argv[sys.argv.index("--url") + 1].rstrip("/")
    args = [a for a in args if a != url]
if len(args) != 3 or args[2] not in ("conforme", "fora", "lavagem"):
    sys.exit(__doc__)
ident, senha, tipo = args

r = requests.post(f"{url}/auth/login", json={"identificador": ident, "senha": senha}, timeout=15)
if r.status_code != 200:
    sys.exit(f"Login falhou: {r.text}")
if r.json()["tipo_usuario"] != "operador_eta":
    sys.exit("Esse usuário não é do tipo operador_eta.")
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
agora = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(tzinfo=None).isoformat()  # hora de Brasília

if tipo == "lavagem":
    resp = requests.post(f"{url}/analise-eta/lavagem-filtro", headers=h, timeout=15,
                         json={"hora": agora, "tempo_gasto_min": 12, "volume_gasto": 3.5})
else:
    valores = ({"turbidez_filtrada": 0.3, "turbidez_tratada": 0.4, "ph_tratada": 7.2, "cloro_residual": 1.1, "cor_tratada": 5}
               if tipo == "conforme" else
               {"turbidez_filtrada": 2.4, "turbidez_tratada": 0.9, "ph_tratada": 5.9, "cloro_residual": 0.1, "cor_tratada": 5,
                "observacoes": "Teste: chuva forte na captação"})
    resp = requests.post(f"{url}/analise-eta/", headers=h, timeout=15, json={"coletado_em": agora, **valores})
print("Enviado." if resp.status_code == 200 else f"Erro {resp.status_code}: {resp.text}")
