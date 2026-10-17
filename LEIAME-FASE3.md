# SIGA — Fase 3: Área do Químico no painel Windows

## O que tem aqui (só os arquivos que mudaram)

    painel_windows/main.py          menu lateral novo, tema azul-marinho, "Área do Químico"
    painel_windows/area_quimico.py  NOVO — a Área do Químico (5 abas)
    painel_windows/tema.py          NOVO — cores do painel num lugar só
    painel_windows/api_client.py    chamadas novas da API de qualidade
    backend/routers/analise_eta_router.py   o químico passa a poder ver as análises da ETA

## Como aplicar

1. Extraia o zip e copie as pastas `painel_windows` e `backend` por cima das suas em
   `C:\Projetos\agua-esgoto` (aceite substituir os 3 arquivos que já existem).
2. Pare o servidor (Ctrl+C) e suba de novo: `python run_server.py` (PowerShell sem o `(venv)`).
3. Abra o painel como sempre. No menu lateral há **Área do Químico**.

## O que a Área do Químico tem

- **Conformidade** — exigido × realizado do mês (Portaria GM/MS 888/2021), situação da rede,
  recoletas pendentes/atrasadas, E. coli da captação, botão **Relatório mensal (PDF)**.
- **Análises da ETA** — as leituras de 2 em 2 horas do operador de ETA, com filtro "só fora do padrão".
  (O botão "Análises ETA" saiu da tela de Estoque e veio pra cá.)
- **Coletas e resultados** — amostras do mês por situação, com detalhes do resultado bacteriológico.
- **Laudos** — laudos de laboratório (inclui o semestral de água bruta): registrar com PDF/foto e abrir.
- **Pontos e regras** — população/filtros da localidade, pontos de coleta, plano de amostragem
  (gerar o mínimo da norma e ajustar regras).

No topo você escolhe a **localidade** e o **mês**. Edição de regras/configuração é só para administrador.

## Aparência

O painel inteiro agora usa azul-marinho (`#0B2A5B`) sobre fundo branco. Para trocar o tom, mude só
`painel_windows/tema.py`. Para o brasão aparecer no menu lateral, salve o arquivo fornecido pela
Prefeitura/SAAE em `painel_windows/assets/brasao.png` (PNG com fundo transparente). Sem o arquivo,
mostra só o nome. A imagem da abertura (`logo_splash.png`) é a antiga e continua como estava.

## Testado

Backend: 16 testes passando. Painel: rodou contra um backend de teste com dados de exemplo, nas
4 localidades, conferindo cada aba e as ações (salvar configuração, gerar plano, editar regra,
cadastrar/desativar ponto, registrar laudo com arquivo, baixar laudo, gerar PDF).
Não testado: o painel empacotado em .exe (PyInstaller) — se for gerar o .exe, lembre que
`area_quimico.py` e `tema.py` entram automaticamente por serem importados.
