# App do Técnico — Água e Esgoto (Android)

App KivyMD pro técnico em campo: vê os chamados atribuídos a ele, inicia o
atendimento e fecha com checklist da situação, materiais utilizados,
descrição e foto tirada na hora pela câmera do celular.

## Modo offline (funciona sem internet)

Como o técnico trabalha em áreas rurais sem sinal, o app **não trava sem
internet**:

- **Login**: precisa de internet na primeira vez (pra buscar seus dados).
  Depois disso, os chamados ficam salvos localmente no celular.
- **Ver chamados**: se não tiver internet, mostra os últimos chamados
  salvos localmente, com um aviso "🔌 Sem internet — mostrando dados salvos".
- **Iniciar atendimento / Fechar chamado**: se não tiver internet, a ação é
  guardada localmente (banco SQLite no próprio celular) e o app segue
  funcionando normalmente, como se tivesse dado certo.
- **Sincronização automática**: toda vez que a tela de chamados é aberta (ou
  atualizada) com internet disponível, o app tenta enviar sozinho tudo que
  ficou pendente. Não precisa fazer nada manualmente — só chegar num lugar
  com sinal e abrir o app (ou puxar pra atualizar).

As fotos tiradas offline ficam salvas no celular e são enviadas junto na
hora da sincronização.

## Fluxo

1. **Login** — telefone/senha
2. **Meus chamados** — lista os atribuídos a você
3. **Detalhe do chamado** → Iniciar atendimento
4. **Checklist da situação encontrada** — marca o que se aplica
5. **Materiais utilizados** — descreve o que foi gasto (nome + quantidade)
6. **Descrição do que foi feito** + **foto** (obrigatória)
7. **Fechar chamado**

## Testar no PC

A câmera nativa (`plyer.camera`) só funciona de verdade no Android — no PC o
app abre normalmente pra você testar login e navegação, mas o botão "Tirar
foto" abre um seletor de arquivo (escolhe qualquer imagem do PC) só pra
simular, já que não tem câmera de celular nesse ambiente.

```bash
cd app_tecnico
python -m venv venv
source venv/bin/activate   # ou venv\Scripts\activate no Windows
pip install -r requirements.txt
```

Configure o endereço da API em `config.py` (`API_BASE_URL`) e rode:

```bash
python main.py
```

## Gerar o APK

Empacotar em KivyMD/Buildozer exige Linux (o Buildozer não roda nativo no
Windows). Duas opções, seguindo o mesmo caminho que já usamos no módulo
Restaurante:

### Opção A — GitHub Actions (recomendado, sem precisar de Linux/WSL local)

1. Suba esta pasta pro seu repositório dentro de uma pasta chamada
   `TecnicoAndroid/` (o workflow em `.github/workflows/build-apk.yml` já
   espera esse nome).
2. Faça push pra branch `main` (ou rode manualmente em Actions → "Build APK -
   Técnico Água" → "Run workflow").
3. O APK fica disponível como artefato do workflow, pronto pra baixar e
   instalar no celular do técnico.

### Opção B — Linux/WSL local

```bash
pip install buildozer
buildozer android debug
```

O APK sai em `bin/tecnicoagua-0.1-arm64-v8a-debug.apk`.

## Observações importantes

- **Permissões**: o app pede internet, câmera e armazenamento — o Android
  vai perguntar ao técnico na primeira vez que ele usar a câmera.
- **Login**: use um usuário do tipo `tecnico` (criado via
  `POST /auth/registrar` no backend).
- **Próximo passo natural**: mover o `API_BASE_URL` fixo em `config.py` pra
  uma tela de configuração dentro do próprio app, assim dá pra trocar o
  endereço do servidor sem gerar um novo APK toda vez.
