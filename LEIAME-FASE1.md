# SIGA — Entrega Fase 0 + Fase 1 (módulo Químico no backend)

Copie as pastas deste pacote por cima do projeto `agua-esgoto` (mesma estrutura de pastas). Só há arquivos novos ou alterados.

## O que mudou
**Fase 0 — base segura**
- `/auth/registrar` (cadastro público) agora SEMPRE cria `cliente`. Antes, qualquer um podia se cadastrar como `admin`.
- Novo `POST /usuarios/` (somente admin) cria admin/operador/técnico/**químico**. O painel Windows já usa essa rota (combo com `quimico`).
- Duplicidade de e-mail/telefone checada só nos campos preenchidos.
- `kivy==2.1.0` nos dois `requirements.txt` dos apps (igual ao `buildozer.spec`).
- Análise de ETA (`/analise-eta`) e lavagem de filtro aceitam o perfil `quimico`, que informa a `localidade`.

**Fase 1 — qualidade da água (Portaria GM/MS 888/2021)**
- Novos arquivos: `qualidade_regras.py` (regras puras da norma), `routers/qualidade_router.py`, `pdf_qualidade.py`; novas tabelas em `models.py` (criadas sozinhas no `create_all`, sem migração).
- Plano de amostragem por localidade gerado da população abastecida/manancial/filtração (editável; edição manual é preservada).
- Pontos de coleta, amostras, resultado bacteriológico (coliformes totais + E. coli), recoletas automáticas (Art. 44 §2), E. coli na captação com média geométrica de 12 meses (limite 1.000), cianobactérias (10.000 / 20.000 cel/mL), laudos do laboratório externo (Viçosa) com arquivo em pasta PRIVADA (`dados_laudos/`, só baixa autenticado).
- Painel de conformidade (exigido × realizado) e PDF mensal.
- Testes: `backend/tests/test_qualidade.py` — `pip install -r requirements-dev.txt` e `python -m pytest tests -q` (14 testes passando).

## Antes de subir no GitHub (importante)
1. Use o `.gitignore` deste pacote. NÃO versionar: `.chave_criptografia_local`, `.secret_key_local`, `siga.db`, `.env`, `uploads/`, `dados_laudos/`, `venv/`, `build/`, `dist/`.
2. Se esses arquivos já foram para o GitHub: troque `SECRET_KEY` (todos terão de logar de novo) e, para a chave de criptografia, é preciso migrar os CPF/CNPJ já cifrados antes de trocá-la — me avise antes de trocar.
3. `seed_dados_teste.py`/`run_seed.py` criam usuários com senha `123456`: não rodar em produção.
4. Defina `CHAVE_CRIPTOGRAFIA` e `SECRET_KEY` no `.env` (veja `backend/.env.example`). Perder a chave = perder os CPF/CNPJ cifrados.

## Pós-instalação
1. Entre como admin → crie o usuário **químico** (painel > cadastrar login, tipo `quimico`).
2. Para cada localidade: `PUT /qualidade/config/{localidade}` (população abastecida, manancial, filtração) → `POST /qualidade/regras/gerar/{localidade}` → cadastre os pontos (captação, saída da ETA, rede, reservatório).
3. Acima de 10.000 hab. abastecidos o mínimo de rede (Anexo 14) deve ser informado manualmente.

## Ressalvas
- Resultados do kit/estufa são controle operacional; a conformidade formal exige laboratório/métodos conforme Arts. 20–22. O laudo de Viçosa fica registrado à parte.
- O PDF do DOU não substitui a versão certificada: confira os números do plano com a Vigilância.
- Análise de ETA de 1 por dia está bem abaixo do mínimo para manancial superficial (12/dia); o painel mostra essa diferença de propósito.
- Nenhuma lógica da norma estadual de MG foi aplicada (base: Portaria 888/2021).
