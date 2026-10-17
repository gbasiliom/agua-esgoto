# SIGA — Entrega Fase 2 (apps Android: Operador de ETA e Químico)

Copie as pastas deste pacote por cima do projeto `agua-esgoto` (mesma estrutura). Este pacote **inclui** tudo da Fase 1 que mudou nesta rodada (perfil novo `operador_eta`, bloqueio de ponto de coleta duplicado). Se você ainda não aplicou o pacote da Fase 0+1, aplique-o antes.

## O que tem
- `app_operador_eta/` — app do operador de cada ETA (perfil `operador_eta`, preso a UMA localidade). Lança a análise a cada 2 h (mostra o relógio da próxima e avisa ATRASADA), lavagem de filtro, alerta imediato dos limites da Portaria 888/2021, **funciona sem sinal** (guarda no aparelho e envia sozinho depois) e mostra histórico/pendências. Lançamento recusado pelo servidor NUNCA é apagado: vai para "recusados".
- `app_quimico/` — app do químico (perfil `quimico`, atende as 4 localidades): painel do mês (exigido × realizado por regra), supervisão de coleta (ponto + finalidade + cloro/cor/turbidez no ato), resultado bacteriológico (coliformes totais e E. coli), recoletas geradas automaticamente, E. coli na captação, cianobactérias, encaminhamento ao laboratório, laudos do laboratório de Viçosa (anexo PDF/foto) e cadastro de pontos de coleta. **Este app precisa de internet** (ver "Limites" abaixo).
- `_comum/` — código compartilhado (tema, login, API, fila offline). Edite aqui e rode `python _comum/sincronizar_comum.py` (cada app leva uma cópia, porque o buildozer só empacota a própria pasta).
- Backend: `operador_eta` entra como perfil interno (localidade obrigatória), pode lançar `/analise-eta` e lavagem de filtro; não acessa `/qualidade`. Painel Windows: combo de "Tipo" inclui `operador_eta`.
- `backend/tests/test_qualidade.py`: 16 testes passando.

## Tema visual
Azul-marinho e branco, igual ao padrão Acordes de Davi. O tom exato do site do SAAE não pôde ser lido (site não abriu para mim): usei `#0B2A5B` — ajuste em `_comum/tema.py` e sincronize.
**Brasão:** não incluí nem desenhei o brasão. Coloque o arquivo oficial (PNG, fundo transparente) em `app_operador_eta/assets/brasao.png` e `app_quimico/assets/brasao.png`; ele aparece sozinho no topo. Sem o arquivo, só aparece o texto. Também falta o ícone (`assets/icone.png`, 512×512): descomente a linha `icon.filename` do `buildozer.spec` quando tiver.

## Como testar no PC (antes de gerar APK)
```
cd backend && python run_server.py            # backend
cd app_operador_eta && pip install -r requirements.txt && python main.py
cd app_quimico      && pip install -r requirements.txt && python main.py
```
Crie os logins pelo painel Windows (tipo `operador_eta` com a localidade; `quimico`). Em cada app, no login, o botão "Servidor: ..." abre o campo para digitar o endereço do backend (ex.: `http://192.168.0.10:8000`) — não precisa recompilar.

## Fluxo de implantação por localidade (admin)
`PUT /qualidade/config/{localidade}` (população abastecida, manancial **superficial**, filtração **lenta**) → `POST /qualidade/regras/gerar/{localidade}`. O químico cadastra os pontos pelo app.
- Informe a população abastecida **de cada localidade** (6.075 é o total de Chalé). Se a sede passar de 5.000, o mínimo de rede sobe de 5 para 10 por mês.
- Sede: captação com bomba — registre isso na descrição do ponto de captação.

## Limites desta entrega (honestos)
1. Os apps foram testados aqui em modo "headless" (PC virtual) contra o backend real: login, lançamentos, fila offline, recoletas, laudo, conformidade. **Não foram compilados em APK nem testados em celular** — o APK sai na Fase 4 (workflow do GitHub Actions refeito por mim) e deve ser testado em aparelho antes de confiar.
2. O app do Químico não tem modo offline: coleta em rio sem sinal precisa ser registrada depois (ou me peça a fila offline também para ele).
3. Envio offline do operador pode, em caso raro de queda de sinal exatamente na resposta do servidor, repetir um lançamento. Duplicado aparece no histórico.
4. A frequência de 12 análises/dia (a cada 2 h) é o mínimo da norma para manancial superficial; o painel vai mostrar "déficit" até o operador cumprir.
5. Qualquer lançamento do químico (kit/estufa) é controle operacional; conformidade formal depende de laboratório/método conforme Arts. 20–22 da Portaria.
