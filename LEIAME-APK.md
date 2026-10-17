# SIGA — gerar os APKs (Android) pelo GitHub Actions

Pacote: siga-apk-workflows.zip. São **4 workflows** (um por app) + ajustes nos `buildozer.spec` + ícone dos apps.

## O que vem aqui
- `.github/workflows/apk-tecnico.yml`, `apk-cliente.yml`, `apk-quimico.yml`, `apk-operador-eta.yml`
- `app_*/buildozer.spec` (corrigidos), `app_*/assets/icone.png` (ícone 512×512 com a logo SAAE)
- `app_tecnico/main.py` e `app_cliente/main.py` (agora pedem a permissão de câmera/arquivos ao abrir o app no Android)

## Correções importantes nos specs (sem elas o build falharia ou o app quebraria)
- `sqlite3` entrou nos requisitos do **técnico** e do **operador de ETA** (os dois guardam dados offline em SQLite).
- `urllib3, chardet, idna, certifi` em todos (o `requests` precisa deles no Android).
- Ícone: o spec apontava para `assets/icone.png`, que não existia → agora existe, nos 4 apps.
- Câmera: técnico e cliente passaram a declarar CAMERA/arquivos e a **pedir a permissão ao abrir** (Android 6+ exige isso).
- `android.accept_sdk_license = True` em todos.

## Passo a passo (uma vez)
1. Repositório do SIGA no GitHub (a raiz do repositório é a pasta que contém `backend`, `painel_windows`, `app_tecnico`...).
2. Extraia o zip por cima da pasta do projeto (C:\Projetos\agua-esgoto) — a pasta oculta `.github` vai junto.
3. PowerShell (na pasta do projeto):
   ```
   git add .
   git commit -m "Workflows de APK"
   git push
   ```
4. (Recomendado) Defina o endereço do servidor para todos os apps: no GitHub, **Settings › Secrets and variables › Actions › Variables › New repository variable**
   → nome `API_BASE_URL`, valor ex.: `https://api.seudominio.com.br` (ou `http://IP:8000` para teste em rede local).
   Sem isso o app vai com o IP de teste `http://192.168.0.115:8000` e só funciona nessa rede.
5. Aba **Actions** › escolha **APK - Técnico** (ou outro) › **Run workflow**. (Pode digitar o endereço do servidor ali na hora.)
6. Espere (primeira vez: 30–60 min; depois usa cache). No fim da execução, em **Artifacts**, baixe o `SIGA-...-apk`, extraia o .apk e instale no celular **Android**
   (permita "instalar apps de fontes desconhecidas"). APK não instala em iPhone.

## O que eu NÃO consegui testar
Não tenho acesso ao GitHub Actions daqui: o conteúdo dos workflows foi montado com base nos problemas que já apareceram nos seus builds
(Docker quebrado, licença do SDK, `libltdl-dev`, Python 3.13/3.14 na imagem, erro 502 no download do freetype, par kivy 2.1.0 + kivymd 1.2.0)
e os arquivos YAML foram validados, mas build de Android costuma pedir 1–3 rodadas de ajuste. Se falhar, me mande o texto do erro (final do log do passo "Gerar o APK").
Também não testei a câmera no aparelho real.

## Ainda por decidir
- Endereço definitivo do servidor (domínio/HTTPS). Enquanto isso, use a variável `API_BASE_URL`.
- Apps do químico e do operador de ETA permitem trocar o servidor na tela de login; técnico e cliente não (usam o endereço embutido).
