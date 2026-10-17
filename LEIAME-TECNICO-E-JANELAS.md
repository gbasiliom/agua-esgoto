# SIGA — janelas na frente (painel Windows) + técnico recebe chamado ao vivo

Extraia **por cima** de C:\Projetos\agua-esgoto (zip: siga-tecnico-janelas.zip).

## 1) Janelas sempre na frente (painel Windows e Painel do Químico)
Novo arquivo `painel_windows/janelas_frente.py`, ligado em `main.py` e `main_quimico.py`. Vale para TODAS as janelas de uma vez
(Novo item, Novo cliente, Novo funcionário, Análises da ETA, Resultado, Laudo, Tarifa, Licitação…), para as caixas de aviso
(messagebox), de "salvar/abrir arquivo" e para a pergunta "Motivo da rejeição":
- cada janela vira "filha" da que a abriu (o Windows a mantém acima da mãe);
- ao abrir é trazida para a frente e recebe o foco;
- avisos e caixas de arquivo abrem presos à janela que está em uso (não vão mais para trás).
Obs.: o teste automático confirma a ligação das janelas e dos avisos; a ordem de empilhamento de verdade só aparece no Windows — se alguma ainda ficar atrás, me diga qual.

## 2) App do técnico: chamado novo ao vivo
A cada 15 s o app (logado) consulta o servidor:
- **Chamado novo atribuído** → aviso na tela (8 s), faixa vermelha "N chamado(s) novo(s) para você!" na tela inicial, o cartão "Chamados" mostra
  "N atendimento(s) aguardando você" e a lista de chamados se atualiza sozinha se estiver aberta.
- **Resposta de solicitação de material** (aprovada/negada, ou compra direta autorizada) → aviso na tela.
- Sem internet: fica em silêncio e continua funcionando offline como antes. Não mexe na fila de sincronização.
Limite: o aviso só aparece com o app aberto (notificação com o celular bloqueado exigiria Firebase/FCM — etapa à parte).

## Testar
1. Servidor: cd backend → python run_server.py
2. Técnico: cd app_tecnico → python main.py (entre como técnico)
3. No painel Windows (cd painel_windows → python main.py): crie um chamado e atribua ao técnico → em até 15 s o app avisa.
4. Janelas: no painel, abra Estoque › Novo item, Clientes › Novo cliente, Gestão › Funcionários etc. — devem abrir na frente.

## Arquivos
painel_windows: janelas_frente.py (novo), main.py, main_quimico.py
app_tecnico: ao_vivo_tecnico.py (novo), main.py, tecnico.kv
