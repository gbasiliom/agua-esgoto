# SIGA — layout v5 (estilo Acordes de Davi) + Painel do Químico separado

Este zip substitui os anteriores (v1 a v4). Extraia **por cima** de C:\Projetos\agua-esgoto.

## Novidades da v5
- **Área do Químico removida do Painel do Administrador** (`main.py`): o menu agora tem só Visão Geral, Operação, Comercial e Gestão.
  O químico usa o **Painel do Químico** (programa separado, `main_quimico.py` / SIGA-Quimico.exe), que continua igual.
- Na Gestão > Novo usuário ainda dá para cadastrar logins do tipo "quimico".

## (histórico) v4 — esta parte foi substituída pela v5
- **Químico fica só com a página dele:** se quem entrar na Área do Químico (pelo Painel do Administrador) for do tipo **químico**,
  o menu dos outros módulos some e só fica a Área do Químico, com o botão "Sair". Ao sair, aparece o login do químico
  (tela cheia); os demais módulos só voltam se um **admin** entrar nessa tela. Se quem entrar for **admin**, segue como antes (painel completo).

## (histórico) v3
- **Visão Geral sem nada do químico:** os cartões das localidades agora mostram chamados em aberto; os atalhos são Estoque, Chamados, Solicitações e Faturamento.
- **Área do Químico no Painel do Administrador pede login toda vez:** ao clicar em "Área do Químico" abre uma janela de e-mail/telefone e senha,
  mesmo com o admin já logado. Aceita químico ou admin; outros tipos recebem "Acesso negado"; "Cancelar" volta para a tela anterior.
  A sessão do químico é separada da sessão do painel.

## Novidades da v2
- **Abertura (splash)** com fundo azul-marinho, logo no cartão branco e botão "Pular ›" (como a intro do Acordes de Davi).
- **Login** no estilo do Acordes: barra superior, cartão central com faixa de título, campos com rótulo, botão "Entrar no Painel" e rodapé.
- **Painel do Químico (programa separado, para Windows):** `painel_windows/main_quimico.py`
  - Login próprio. Aceita só usuário tipo **químico** (e **admin**, para suporte). Operador/técnico/cliente recebem "Acesso negado".
  - Mostra só a Área do Químico (conformidade, análises da ETA, coletas e resultados, laudos, pontos e regras).
  - Para abrir: dois cliques em `painel_windows\iniciar_painel_quimico.bat` ou `python main_quimico.py`.
  - Para aceitar SOMENTE químico (sem admin): em main_quimico.py troque `TIPOS_ACEITOS = ("quimico", "admin")` por `("quimico",)`.
- O Painel do Administrador (`main.py`) NÃO tem mais a Área do Químico (v5).
- Logo SAAE Chalé em todos os apps (arquivo assets/logo_saae.png).

## Como testar (PowerShell)
1. Servidor:  cd C:\Projetos\agua-esgoto\backend  →  python run_server.py   (deixe aberto)
2. Painel admin:   cd C:\Projetos\agua-esgoto\painel_windows  →  python main.py
3. Painel químico: cd C:\Projetos\agua-esgoto\painel_windows  →  python main_quimico.py
   (entre com um usuário químico; teste também com um operador para ver o "Acesso negado")
4. Apps: python main.py dentro de cada pasta app_*.

## Arquivos novos/alterados
painel_windows: main.py, main_quimico.py (novo), layout_comum.py (novo), iniciar_painel_quimico.bat (novo),
area_quimico.py, tema.py, visao_geral.py, assets/logo_saae.png
_comum + app_operador_eta + app_quimico: tema.py, base_app.py, kv_comum.kv, kv_layout.kv, telas_*.kv, assets/logo_saae.png
app_tecnico + app_cliente: main.py, *.kv, kv_layout.kv, assets/logo_saae.png

## Brasão
Se existir assets/brasao.png, aparece ao lado da logo. Eu não desenho o brasão.
