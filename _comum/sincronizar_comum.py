"""Copia os arquivos comuns (tema, API base, fila offline...) para as pastas dos apps.
Cada app precisa de uma cópia porque o buildozer só empacota a própria pasta.
Edite SEMPRE em _comum/ e rode:  python _comum/sincronizar_comum.py"""
import os
import shutil

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
COMUNS = {
    "app_operador_eta": ["tema.py", "async_helper.py", "config.py", "api_base.py", "base_app.py", "fila_local.py", "kv_comum.kv", "kv_layout.kv", "sessao_http.py", "fluxo_senha.py", "seguranca_telas.py", "kv_seguranca.kv"],
    "app_quimico": ["tema.py", "async_helper.py", "config.py", "api_base.py", "base_app.py", "kv_comum.kv", "kv_layout.kv", "sessao_http.py", "fluxo_senha.py", "seguranca_telas.py", "kv_seguranca.kv"],
    "app_tecnico": ["tema.py", "async_helper.py", "config.py", "api_base.py", "base_app.py", "kv_comum.kv", "kv_layout.kv", "sessao_http.py", "fluxo_senha.py", "seguranca_telas.py", "kv_seguranca.kv"],
    "painel_windows": ["sessao_http.py"],
    "app_cliente": ["tema.py", "async_helper.py", "config.py", "api_base.py", "base_app.py", "kv_comum.kv", "kv_layout.kv", "sessao_http.py", "fluxo_senha.py", "seguranca_telas.py", "kv_seguranca.kv"],
}
for app, arquivos in COMUNS.items():
    for a in arquivos:
        shutil.copy2(os.path.join(AQUI, a), os.path.join(RAIZ, app, a))
        print(f"{a} -> {app}/")
