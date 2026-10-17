# SIGA — Químico recebe as análises da ETA ao vivo

Extraia **por cima** de C:\Projetos\agua-esgoto (zip: siga-ao-vivo.zip). Precisa reiniciar o **servidor** (backend) — as telas novas dependem dele.

## Como funciona
O operador da ETA já enviava cada análise/lavagem ao servidor (com fila offline no celular). Agora o servidor tem o endpoint
`GET /analise-eta/ao-vivo` e o Painel do Químico (Windows) e o app do Químico (Android) consultam **a cada 15 segundos**,
recebendo só o que for novo. O app do operador de ETA **não mudou**.

- **Painel do Químico (Windows):** nova aba **"Ao vivo"** (primeira aba): situação das 4 ETAs + lista dos últimos lançamentos com etiqueta NOVA.
  A **faixa de alertas** no topo aparece em qualquer aba e o computador **apita** quando surge um problema novo. A aba "Análises da ETA" se atualiza sozinha.
- **App Android do Químico:** botão **"Ao vivo (ETAs)"** na tela inicial, alerta vermelho na tela inicial e um aviso na tela quando surge um problema novo (com o app aberto).

## Alertas
1. **Fora do padrão** — a última análise da ETA passou de algum limite da Portaria GM/MS 888/2021 (turbidez, pH, cloro, cor).
2. **Análise atrasada** — mais de 2h20 sem coleta (2h do intervalo + 20 min de tolerância), **só dentro do turno** (padrão 06:00–20:00, horário de Brasília).
   No começo do turno a contagem parte das 06:00. Para mudar o turno, defina no servidor as variáveis `ETA_TURNO_INICIO` e `ETA_TURNO_FIM` (horas, ex.: 7 e 18).
3. **Lavagem de filtro** aparece na lista assim que o operador lança.

## Limites (honestos)
- É consulta a cada 15 s, não push instantâneo: o atraso é de até ~15 s (suficiente para análises de 2 em 2 horas).
- No Android o aviso só aparece **com o app aberto**. Notificação com o celular bloqueado/app fechado exigiria Firebase (FCM) — é uma etapa à parte.
- Se o operador estiver sem internet, o dado só chega quando o celular dele sincronizar (o painel então mostra "atrasada" até lá).

## Testar (PowerShell)
1. Servidor: cd backend → python run_server.py (reinicie)
2. Painel do Químico: cd painel_windows → python main_quimico.py → entre como químico → aba "Ao vivo"
3. App químico: cd app_quimico → python main.py
4. Lance uma análise no app do operador da ETA (app_operador_eta) e veja aparecer em até 15 s. Teste uma com turbidez filtrada acima de 1,0 para ver o alerta.
4b. Sem celular? Em outro PowerShell: cd backend → python simular_operador_eta.py TELEFONE SENHA fora   (ou `conforme` / `lavagem`; TELEFONE/SENHA de um login operador_eta)
5. Testes automáticos do servidor: cd backend → python -m pytest tests -q (20 passam)

## Arquivos
backend: routers/analise_eta_router.py, tests/test_ao_vivo.py, simular_operador_eta.py (novo — simula o operador para testar sem celular)
painel_windows: ao_vivo.py (novo), area_quimico.py, api_client.py
app_quimico: ao_vivo_util.py (novo), main.py, api_client.py, telas_quimico.kv
