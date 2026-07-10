# Guia Prático: Importar SSO no Grok Desktop

> 🧑‍💻 Se você é leigo, comece por aqui.
>
> **Status 2026-07-09:** SSO import (UI / arquivo / `sso-watch` / `POST /v1/sso`) está
> **implementado** na `main`. Auto-registro nativo: `grok-signup-bot/` +
> [`auto-register-plan-v1.md`](../plan/executed/auto-register-plan-v1.md).  
> Auditoria: [`FINDINGS.md`](../plan/executed/FINDINGS.md) · Hardening: [`hardening-plan-v1.md`](../plan/open/hardening-plan-v1.md).

## O que essa feature faz

Permite importar **tokens SSO** (criados por ferramentas como grok-register) diretamente no Grok Desktop, sem precisar fazer login manual no navegador.

## Como executar (passo a passo)

### 1. Compilar o app com a nova feature

No terminal, dentro da pasta do projeto:

```bash
wails build
```

Isso gera o executável `GrokDesktop` na pasta `build/bin/`.

### 2. Iniciar o Grok Desktop

Execute o `GrokDesktop` compilado. A interface abre normalmente.

### 3. Importar os SSO tokens

Você tem **3 formas**, da mais manual à mais automática:

#### 🔵 A) Colar um token (mais simples)

Na sidebar:
1. Clique em **"Importar SSO"**
2. Cole o token SSO (aquele texto longo)
3. A conta aparece na lista

#### 🟡 B) Importar de arquivo (lote)

Se você tem um arquivo com vários tokens (um por linha):
1. Clique em **"Importar de arquivo"**
2. Digite o caminho do arquivo (ex: `/home/voce/tokens.txt`)
3. Todos os tokens são importados de uma vez

#### 🟢 C) Via HTTP (automático, para desenvolvedores)

Com o proxy rodando (`http://127.0.0.1:8787`), envie os tokens via curl:

```bash
curl -X POST http://127.0.0.1:8787/v1/sso \
  -H "Content-Type: application/json" \
  -d '{"token":"SEU_SSO_AQUI"}'
```

Pode enviar vários de uma vez:
```json
{"tokens": ["sso1", "sso2", "sso3"]}
```

### 4. Usar a conta

Na sidebar, clique em **"Usar"** na conta importada. Agora é só conversar.

---

> **Precisa de ajuda para gerar os SSO tokens?** O grok-register (https://github.com/Florisheedless915/grok-register) cria contas xAI automaticamente. O Guia abaixo tem mais detalhes sobre ele.

---

# Análise de Integração: grok-register → grok-proxy-plus

## 1. Repositórios Analisados

### 1.1 Always15dppk/register (original)

https://github.com/Always15dppk/register/tree/main/grok-register

Robô de registro automatizado no **xAI/Grok**. Escrito em **Python 3.10+**.

**Fluxo:**
1. Cria email descartável via **Mail.tm** (API pública gratuita)
2. Envia requisição gRPC-web para `accounts.x.ai/auth_mgmt.AuthManagement/CreateEmailValidationCode`
3. Pega o código de verificação do email via API do Mail.tm
4. Verifica o código via gRPC-web (`VerifyEmailValidationCode`)
5. Resolve Cloudflare **Turnstile** via **YesCaptcha** (serviço pago)
6. Submete formulário de registro via HTTP para `accounts.x.ai/sign-up`
7. Extrai **SSO token** do cookie
8. Salva em `keys/grok.txt` e `keys/accounts.txt`

**Dependências:** `curl_cffi`, `beautifulsoup4`, `requests`, `python-dotenv`, **YesCaptcha** (pago)

### 1.2 Florisheedless915/grok-register (fork avançado)

https://github.com/Florisheedless915/grok-register

**Diferenças cruciais do original:**

| Aspecto | Original | Fork avançado |
|---------|----------|---------------|
| **Abordagem** | HTTP/gRPC puro | **Browser automation** (DrissionPage) |
| **Turnstile** | YesCaptcha (pago) | **Extensão Chrome** + `turnstilePatch/` (grátis) |
| **Email** | Mail.tm (público) | **DuckMail** (auto-hospedado) |
| **Interface** | CLI apenas | **Web UI** + batch runner |
| **Rede** | Proxy opcional | **WARP egress** integrado |
| **Token sink** | Arquivo local | **grok2api** endpoint |
| **Deploy** | Script manual | **Docker Compose** |
| **Runtime** | Python 3.10+ | Python 3.12+ (DrissionPage) |

**Fluxo (DrissionPage_example.py):**
1. Inicia navegador Chromium real com perfil temporário independente
2. Abre `https://accounts.x.ai/sign-up?redirect=grok-com`
3. Clica em "Usar email para registrar"
4. Cria email temporário via DuckMail
5. Preenche email e submete (via JS, com dispatchers de evento React)
6. Aguarda código de verificação no DuckMail e preenche automaticamente
7. Resolve Turnstile via **extensão Chrome** que faz patch de `MouseEvent.screenX/screenY` + clique automatizado
8. Gera perfil aleatório (nome + senha) e preenche formulário final
9. Extrai cookie `sso` após registro bem-sucedido
10. Salva em `sso/sso_<data>.txt` e/ou envia para API grok2api

**Como resolve Turnstile sem YesCaptcha:**
- Extensão em `turnstilePatch/` que manipula os eventos de mouse no Shadow DOM do iframe do Turnstile
- Script injeta `Object.defineProperty(MouseEvent.prototype, 'screenX', { value: ... })` para contornar detecção de automação
- Clica no checkbox do Turnstile dentro do iframe
- Não precisa de serviço externo — é **gratuito**

---

## 2. O que é o grok-proxy-plus

Aplicação **desktop** (Go + Wails v2) que:

- Autentica contas xAI via **OAuth 2.0 Device Authorization Grant** (RFC 8628)
- Expõe proxy local **OpenAI-compatible** em `http://127.0.0.1:8787/v1`
- Fornece UI de chat com streaming, search tools, histórico
- Suporta múltiplas contas xAI (armazenadas como JSON em AppData)
- Pode **importar SSO** e **auto-registrar** (experimental; ver FINDINGS H1–H3)

### Stack

- **Backend:** Go 1.25
- **Frontend:** Vanilla JS + Vite
- **Desktop:** Wails v2.13
- **Armazenamento:** JSON files em AppData (sem banco de dados)

---

## 3. Análise de Integração

### Desafios

| Aspecto | Detalhe |
|---------|---------|
| **Linguagem** | grok-register é **Python**, grok-proxy-plus é **Go** |
| **Dependências** | `curl_cffi` (sem equivalente Go para fingerprint TLS), YesCaptcha (pago), Mail.tm |
| **Fragilidade** | Scraping da página de registro do xAI — quebra se frontend mudar |
| **ToS** | Registro automatizado provavelmente viola Termos de Serviço do xAI |
| **Packaging** | Empacotar Python + dependências num app Wails aumenta complexidade |

### Possíveis Abordagens

#### A — Wrapper Python (subprocesso)
- Botão "Criar conta" na UI → chama `python grok.py` em background
- Prós: código existente funciona, mínimo esforço
- Contras: usuário precisa ter Python + dependências + YesCaptcha key

#### B — Reimplementar em Go
- Portar a lógica gRPC-web + email + captcha para Go nativo
- Prós: totalmente integrado
- Contras: muito trabalho, sem equivalente Go para `curl_cffi` (fingerprint TLS)

#### C — CLI separada + importação de SSO
- Manter grok-register como ferramenta independente
- Adicionar na UI um botão "Importar SSO" que lê `keys/grok.txt`
- Prós: zero risco de quebrar o app, cada ferramenta no seu nicho
- Contras: fluxo menos integrado

#### D — Serviço interno Python
- Criar microsserviço Python que roda junto com o app Go
- Comunicação via HTTP local
- Prós: isolamento, reutilização do código Python
- Contras: mais um processo para gerenciar

---

## 4. Turnstile: kitty-browser e outras alternativas

### 4.1 kitty-browser

https://github.com/lan2334/kitty-browser

Biblioteca **Node.js** (Puppeteer/cloakbrowser) com `turnstile: true` que automatiza clique no Turnstile.

**Relevância:** o fork do Florisheedless915 já resolve Turnstile sem YesCaptcha via extensão Chrome + DrissionPage (Python). kitty-browser seria irrelevante nesse contexto — a solução já existe em Python.

### 4.2 Como o fork resolve Turnstile (gratuito)

O diretório `turnstilePatch/` contém uma extensão Chrome que:
1. Injeta JS no iframe do Turnstile
2. Patcheia `MouseEvent.screenX/screenY` para valores realistas
3. Clica automaticamente no checkbox do Turnstile
4. Extrai o token via `turnstile.getResponse()`

Tudo em Python + DrissionPage, sem serviços pagos.

---

## 5. Recomendação Final

**O fork do Florisheedless915 é a melhor base** para integração com o grok-proxy-plus:

### Vantagens sobre o original

| Problema | Original | Fork | 
|----------|----------|------|
| YesCaptcha pago | Obrigatório | **Resolvido** (extensão Chrome grátis) |
| Mail.tm público (instável) | Obrigatório | **DuckMail** auto-hospedado |
| Sem interface | CLI apenas | **Web UI** + batch runner |
| Tokens só em arquivo | Local | **grok2api push** integrado |
| Sem deploy | Script manual | **Docker Compose** |

### Abordagem recomendada

**Opção C+ (CLI Docker + importação SSO):**

1. **Deploy do fork via Docker** no mesmo servidor:
   ```bash
   git clone https://github.com/Florisheedless915/grok-register
   cd grok-register
   docker compose up -d
   ```
2. **Configurar DuckMail** (email temporário) + grok2api (receber SSO)
3. **No grok-proxy-plus**: adicionar botão "Importar SSO" que:
   - Lê `grok-register/sso/sso_*.txt`
   - Chama o OAuth flow com o SSO token para obter refresh/access token
   - Salva como conta normal no store

### Fluxo completo

```
grok-register (Docker)                 grok-proxy-plus (Desktop)
        │                                      │
        │── Cria contas xAI ──────────────────→│
        │   (SSO tokens)                       │
        │                                      │── Importa SSO
        │                                      │── OAuth exchange
        │                                      │── Salva conta
        │                                      │── Pronto pra usar
```

Se quiser ainda mais integração, a **Opção A (wrapper)** poderia chamar o container Docker da CLI do Python via subprocesso e importar automaticamente — mas a Opção C+ já resolve 90% do problema com zero acoplamento entre os projetos.

---

## 6. Tutorial Passo a Passo

### Cenário 1: Importar manual (rápido)

1. **Rode o grok-register** (Docker ou Python) para gerar SSO tokens
2. Abra o **Grok Desktop**
3. Na sidebar, clique **"Importar SSO"**
4. Cole o token (de `sso/sso_*.txt` ou `keys/grok.txt`)
5. A conta aparece na lista e já fica ativa

### Cenário 2: Importar de arquivo (lote)

1. Com o arquivo de SSO em mãos (ex: `sso_20260709_143000.txt`)
2. No Grok Desktop, clique **"Importar de arquivo"**
3. Digite o caminho completo do arquivo
   ```
   /home/seuuser/grok-register/sso/sso_20260709_143000.txt
   ```
4. Todos os tokens do arquivo são importados de uma vez

O arquivo pode estar nos formatos:
- Apenas SSO: `sso_token_aqui` (uma por linha)
- `email:password:SSO` (formato `accounts.txt`)

### Cenário 3: HTTP endpoint (E2E real, zero toque)

O proxy do Grok Desktop expõe `POST /v1/sso` para receber tokens direto via HTTP.

**Passo único:** configure o grok-register para enviar tokens ao final do batch:

```bash
# No script pós-batch do grok-register
for token in $(cat sso/sso_*.txt); do
  curl -s -X POST http://127.0.0.1:8787/v1/sso \
    -H "Content-Type: application/json" \
    -d "{\"token\":\"$token\"}"
done
```

Ou envie todos de uma vez:
```bash
curl -s -X POST http://127.0.0.1:8787/v1/sso \
  -H "Content-Type: application/json" \
  -d "$(jq -Rs '{tokens: split("\n") | map(select(length > 0))}' sso/sso_*.txt)"
```

**Payload aceitos:**
```json
{"token": "sso_token_aqui"}
{"tokens": ["sso1", "sso2", "sso3"]}
```

**Sem arquivo, sem pasta, sem copiar.** O proxy recebe e importa na hora.

### Fluxo E2E completo (zero toque)

```
1. docker compose up -d          # sobe grok-register + DuckMail + WARP
2. Abre web UI do grok-register  # http://localhost:18600
3. Configura e inicia o batch    # gera SSO tokens em sso/*.txt
4. # Opcional: copia automática via script pós-batch
   cp sso/*.txt ~/.local/share/GrokDesktop/sso-watch/
5. Grok Desktop detecta sozinho  # watchdog a cada 30s
6. Contas prontas pra usar       # seleciona no menu de contas
```

### Verificar se funcionou

- Na sidebar do Grok Desktop, o número de contas aumenta
- A conta importada aparece com label `SSO <email>` ou `SSO <id>`
- Selecione a conta e envie uma mensagem
