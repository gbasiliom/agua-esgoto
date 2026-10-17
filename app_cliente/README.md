# App do Cliente/Morador — Água e Esgoto (Android)

App KivyMD pro morador: cria conta, completa o endereço, abre chamados e
acompanha o status de cada um.

## Fluxo

1. **Criar conta** — nome, telefone, senha
2. **Completar cadastro** — endereço, bairro, cidade, hidrômetro (só na primeira vez)
3. **Abrir chamado** — tipo de problema, prioridade, descrição
4. **Meus chamados** — acompanha o status (aberto → atribuído → em andamento → concluído)

## Testar no PC

```bash
cd app_cliente
python -m venv venv
venv\Scripts\activate      # ou source venv/bin/activate no Linux/Mac
pip install -r requirements.txt
python main.py
```

Configure o `API_BASE_URL` em `config.py` (padrão `http://127.0.0.1:8000`,
pra testar no mesmo PC onde o backend está rodando).

## Gerar o APK

Mesmo caminho dos outros apps da A'Guilda — sobe a pasta como `ClienteAndroid/`
no repositório (o workflow em `.github/workflows/build-apk.yml` já espera
esse nome) e roda o GitHub Actions, ou usa Buildozer local em Linux/WSL:

```bash
pip install buildozer
buildozer android debug
```
