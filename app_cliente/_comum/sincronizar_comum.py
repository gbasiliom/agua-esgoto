"""Copia os arquivos comuns (tema, API base, fila offline...) para as pastas dos apps.
Cada app precisa de uma cópia porque o buildozer só empacota a própria pasta.
Edite SEMPRE em _comum/ e rode:  python _comum/sincronizar_comum.py"""
import os
import shutil

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
COMUNS = {
    "app_operador_eta": ["tema.py", "async_helper.py", "config.py", "api_base.py", "base_app.py", "fila_local.py", "kv_comum.kv"],
    "app_quimico": ["tema.py", "async_helper.py", "config.py", "api_base.py", "base_app.py", "kv_comum.kv"],
}
for app, arquivos in COMUNS.items():
    for a in arquivos:
        shutil.copy2(os.path.join(AQUI, a), os.path.join(RAIZ, app, a))
        print(f"{a} -> {app}/")
