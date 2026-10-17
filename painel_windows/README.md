# Painel Windows — Água e Esgoto

App desktop (CustomTkinter) pro admin/operador: dashboard com KPIs, lista de
chamados e atribuição de técnico.

## Como rodar

```bash
cd painel_windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Configure o endereço da API (padrão `http://localhost:8000`). Se o backend
estiver em outra máquina da rede, defina a variável de ambiente antes de
rodar, ou edite `config.py`:

```
set API_BASE_URL=http://192.168.1.10:8000
python main.py
```

## Gerar o .exe (rodar no seu Windows, não dá pra gerar por aqui)

```powershell
venv\Scripts\activate
pip install pyinstaller
pyinstaller --onefile --windowed --name "SIGA" --icon "assets\icone.ico" --add-data "assets;assets" main.py
```

O executável fica em `dist\SIGA.exe`. O `--add-data "assets;assets"` é
essencial — sem ele, o `.exe` não encontra o logo/splash e quebra ao abrir
(a pasta `assets` precisa ser copiada junto pro pacote final).

**Teste sempre o `.exe` gerado antes de distribuir** — abre ele de dentro da
pasta `dist\` (dá um duplo-clique) pra confirmar que abre normal, loga, e
mostra o logo certinho.

## Login

Use um usuário do tipo `admin` ou `operador` (criado via `POST /auth/registrar`
no backend). Só esses dois tipos conseguem entrar neste painel.
