# Backend — Sistema de Água e Esgoto

API 100% Python (FastAPI + PostgreSQL) que serve como banco central para:
- Painel Windows (dispatcher)
- App do cliente (Android)
- App do técnico (Android)
- Futuramente, o bot de WhatsApp

## Como rodar (localmente, pra testar)

```bash
cd backend
python -m venv venv
source venv/bin/activate   # no Windows: venv\Scripts\activate
pip install -r requirements.txt
python migrar_bd.py
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Não precisa configurar nada** — por padrão já roda em **SQLite** (um
arquivo `siga.db`, criado sozinho na pasta `backend/`). Zero instalação,
zero servidor de banco separado.

### Quer usar PostgreSQL em vez de SQLite?

Cria um arquivo `.env` na pasta `backend/`:
```
DATABASE_URL=postgresql://usuario:SUA_SENHA@localhost:5432/agua_esgoto
```

**O sistema é o mesmo código nos dois casos** — SQLite e Postgres têm
exatamente as mesmas funcionalidades, tabelas e comportamento. A única
diferença é o "motor" por trás. Dá pra migrar de um pro outro a qualquer
momento — é só isso que muda no `.env`, sem reescrever nada.

**Quando escolher qual:**
- **SQLite** (padrão): mais simples, sem instalar nada, ótimo pra começar
  e pra um volume pequeno/médio de uso (o cenário de hoje)
- **PostgreSQL**: quando o sistema crescer bastante (muita gente mexendo
  ao mesmo tempo) ou se quiserem recursos mais avançados de banco

## Segurança

### Chaves — configure no `.env` (produção de verdade)

```
SECRET_KEY=<gere com: python -c "import secrets; print(secrets.token_urlsafe(64))">
CHAVE_CRIPTOGRAFIA=<gere com: python criptografia.py>
```

**Sem essas variáveis definidas, o sistema gera e salva as chaves em
arquivos locais (`.secret_key_local` e `.chave_criptografia_local`) — funciona,
mas fica menos portátil.** O que importa de verdade: **nunca perca a
`CHAVE_CRIPTOGRAFIA`** depois que já tiver CPF/CNPJ salvos — sem ela, esses
dados ficam permanentemente ilegíveis (é assim que criptografia funciona,
não tem "esqueci minha senha"). Faça backup dessa chave em lugar seguro,
separado do banco de dados.

### O que já está protegido
- **Senhas**: hash bcrypt (irreversível, nem nós conseguimos ver a senha original)
- **CPF/CNPJ**: criptografado no banco com AES-256-GCM (autenticado) — quem
  abrir o banco direto só vê texto cifrado, não o CPF
- **Login**: token assinado (JWT) com chave forte gerada automaticamente

### O que depende de infraestrutura (não dá pra resolver só no código)
- **HTTPS/TLS** (cadeado no navegador, tráfego criptografado entre o
  celular/PC e o servidor): hoje a API roda em `http://` puro. Pra ter
  HTTPS de verdade, precisa de um domínio próprio + certificado (grátis
  via [Let's Encrypt](https://letsencrypt.org)) + um proxy reverso (nginx
  ou Caddy) na frente do `uvicorn`. Isso é configuração do servidor onde
  o backend for hospedado, não uma biblioteca Python — me avise quando
  tiverem o servidor/domínio definitivo que ajudo a configurar isso.
- **Backup do banco**: criptografia não substitui backup — faça backups
  regulares do Postgres em local seguro.

## Importante: pro técnico acessar de qualquer lugar via dados móveis

Isso que você descreveu — o técnico na rua, longe da oficina, mandando e
recebendo pelo 4G/3G — é exatamente pra isso que a API existe. Mas tem um
detalhe de rede que precisa resolver, senão só funciona quando o celular
está no mesmo Wi-Fi do computador:

- **Um IP tipo `192.168.1.10`** só é visível dentro da mesma rede local
  (mesmo Wi-Fi/roteador). Fora dela — no 4G, na rua — o celular não
  enxerga esse endereço de jeito nenhum.
- Pra funcionar de qualquer lugar, o servidor (o computador da oficina, ou
  onde o `uvicorn` estiver rodando) precisa ter um **endereço acessível pela
  internet**. Duas formas de resolver isso:

  **Opção A — Liberar o computador da oficina pra internet** (fica tudo
  onde já está, sem custo de servidor):
  - No roteador da oficina, configura **redirecionamento de porta** (port
    forwarding) da porta 8000 pro computador onde a API roda.
  - Como IP residencial normalmente muda de tempos em tempos, usa um
    serviço de **DNS dinâmico** (ex: No-IP, DuckDNS, gratuitos) pra ter um
    endereço fixo tipo `oficina.duckdns.org` em vez de decorar números.
  - O computador da oficina precisa ficar ligado o tempo todo pra isso
    funcionar.

  **Opção B — Uma VPS bem simples** (mais estável, recomendo pra produção
  de verdade): um servidor alugado (~R$25-40/mês, ex: DigitalOcean, Contabo,
  Hetzner) que já nasce com IP público fixo, sem depender do computador da
  oficina estar ligado. O backend roda lá, com Postgres também instalado
  nela.

Qualquer uma das duas funciona com o código como está — só muda o que você
coloca no `API_BASE_URL` dos apps (o IP/domínio público em vez do IP local).

## Rotas principais

| Rota | Método | Quem usa | O que faz |
|---|---|---|---|
| `/auth/registrar` | POST | Todos | Cria conta (cliente, técnico, operador) |
| `/auth/login` | POST | Todos | Login, retorna token |
| `/chamados/` | POST | App cliente / painel | Abre um chamado |
| `/chamados/` | GET | Painel / app técnico | Lista chamados (filtra por status/técnico) |
| `/chamados/{id}/atribuir` | PATCH | Painel Windows | Atribui um técnico |
| `/chamados/{id}/iniciar` | PATCH | App técnico | Marca início do atendimento |
| `/chamados/{id}/fechar` | POST | App técnico | Fecha com descrição + foto(s) |
| `/chamados/relatorio/resumo` | GET | Painel Windows | KPIs pro dashboard |

Documentação interativa automática em `http://localhost:8000/docs`.

## Próximos passos sugeridos

1. **Hospedagem definitiva**: uma VPS simples (ex: um servidor de ~R$25-40/mês)
   ou o próprio servidor da prefeitura, sempre ligado e com IP acessível.
2. **Painel Windows** (CustomTkinter): consome `/chamados/`, `/chamados/{id}/atribuir`
   e `/chamados/relatorio/resumo`.
3. **App do técnico** (KivyMD/Buildozer): consome `/chamados/?tecnico_id=...`,
   `/chamados/{id}/iniciar` e `/chamados/{id}/fechar` (com foto da câmera).
4. **App do cliente** (KivyMD/Buildozer): consome `/auth` e `POST /chamados/`.
5. **Bot de WhatsApp**: serviço à parte que recebe mensagens (Meta Cloud API)
   e chama `POST /chamados/` com `origem="whatsapp"`.
