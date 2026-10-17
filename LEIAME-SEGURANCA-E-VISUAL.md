# SIGA — Pacote completo: segurança + visual azul-marinho + hidrômetro só na sede

## O que mudou

**Segurança (servidor, painel e os 5 apps)**
- Recuperar senha pelo e-mail com código de 6 dígitos ("Esqueci minha senha" em todos os apps e no painel).
- Senha provisória (criada pelo admin ou resetada): a pessoa é obrigada a trocar no primeiro acesso.
- Sessão curta (30 min) que se renova sozinha; "Sair" derruba o aparelho no servidor; trocar a senha desconecta os outros aparelhos.
- Bloqueio de 15 min após 5 senhas erradas; limite de tentativas por aparelho.
- Administrador entra com código por e-mail (liga sozinho quando o envio de e-mail estiver configurado).
- Auditoria de segurança (quem entrou, senhas erradas, bloqueios, resets) na aba Segurança do painel.
- Correções de acesso: morador só vê os próprios chamados/faturas/PDFs; fotos e arquivos (`/uploads`) agora exigem login; técnico só vê os próprios chamados.
- Cadastro de morador exige e-mail (é por ele que recupera a senha).

**Painel Windows**
- Barra fina, só administração: Resumo · Clientes · Faturamento (Faturas/Leituras) · Financeiro · Licitações · Equipe · Segurança (Acessos/Auditoria).
- Chamados, Solicitações e Estoque ficam no menu do seu nome (canto direito), junto com "Trocar senha" e "Sair".
- Resumo novo: 4 números, lista "Precisa da sua atenção" e tabela por localidade. Sem frases, banners nem rodapé.
- Segurança > Acessos: lista de contas, busca, "Resetar senha" (gera senha provisória mostrada uma vez) e "+ Novo login" (sem senha digitada = o servidor gera uma provisória).

**Apps (técnico, morador, químico, operador de ETA)**
- Visual azul-marinho padrão (cabeçalho marinho, cartões brancos com borda fina, rótulos pequenos em maiúsculas, botão principal marinho).
- Campo "Servidor" no login (não precisa mais recompilar para trocar o IP).
- App do morador: leitura e faturas só aparecem para moradores da **Sede**.

**Regra: hidrômetro só na Sede**
- Fora da Sede o hidrômetro não é gravado, a leitura é recusada e não existe fatura. Penha do Coco, Bananal e Água Limpa usam o sistema só para cadastro e chamados.

**Correção de erro antigo:** o morador não conseguia editar o próprio cadastro depois de criado.

## Como instalar (PowerShell)

```powershell
# 1) Backup do projeto (sempre!)
cd C:\Projetos
Copy-Item -Recurse agua-esgoto agua-esgoto-backup

# 2) Copiar o pacote por cima do projeto (não apaga seu banco, seu .env nem seus venvs)
Expand-Archive -Force "$env:USERPROFILE\Downloads\siga-pacote-completo.zip" -DestinationPath C:\Projetos\agua-esgoto

# 3) Servidor
cd C:\Projetos\agua-esgoto\backend
Copy-Item .env.example .env -ErrorAction SilentlyContinue   # só se ainda não tiver .env
.\venv312\Scripts\activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

O banco se atualiza sozinho ao ligar o servidor (colunas novas de segurança). Para testar com as senhas simples (123456), deixe `SIGA_MODO_TESTE=1` no `.env`. **Em produção, apague essa linha.**

```powershell
# 4) Painel (outra janela do PowerShell)
cd C:\Projetos\agua-esgoto\painel_windows
$env:API_BASE_URL="http://127.0.0.1:8000"
python main.py

# 5) Apps (outra janela; use o venv compartilhado dos apps)
cd C:\Projetos\agua-esgoto\app_tecnico      # ou app_cliente, app_quimico, app_operador_eta
python main.py
```

No celular, no login do app toque em "Servidor: ..." e digite o endereço do servidor (ex.: `http://192.168.0.115:8000`).

## E-mail do código de recuperação
- Sem configurar nada, o código aparece no console do servidor (serve para testar).
- Para enviar de verdade: preencha `RESEND_API_KEY` e `EMAIL_REMETENTE` (ou `SMTP_*`) no `.env`. O Resend exige verificar um domínio seu para enviar a qualquer pessoa.
- O código de 2 etapas do admin só liga quando o envio de e-mail estiver configurado.

## Atenção
- Quem hoje tem senha fraca (ex.: 123456) será obrigado a trocar no próximo login, a não ser com `SIGA_MODO_TESTE=1`.
- Morador antigo sem e-mail não recupera a senha sozinho: use Segurança > Acessos > "Resetar senha".
- Administrador novo precisa de e-mail cadastrado.
- Se você tiver o `estoque_router.py` com ajustes seus, confira o `@router.post("/movimentar")` depois de copiar.

## Testes
- Servidor: 48 testes automáticos passando (segurança, permissões, hidrômetro só na Sede).
- Telas conferidas em teste: entrar, esqueci/redefinir senha, troca obrigatória, sair, cadastro de morador, Sede x Bananal.
