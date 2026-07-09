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
- **Não tem capacidade de criar contas** — usuário precisa já ter conta xAI

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
