# Plano: Auto-registro de conta xAI via Device Login + bot Playwright

> Substitui o plano v0 (`auto-register-plan-v0.md`), que extraía cookie SSO —
> abordagem quebrada (SSO é cookie de sessão web e não funciona como Bearer no
> upstream). Este plano usa o **Device Login OAuth** (já funciona na `main`) e
> devolve um JWT legítimo.

## Visão geral

Botão "Criar conta" no Grok Desktop → o **Go** dispara o Device Login OAuth
(já existe), passa a **verification URL** (e opcionalmente `user_code`) para um
**bot Python (Playwright)** que automatiza o browser: abre a URL do device →
signup com email temporário (provider pluggable) → lê OTP via API → preenche
nome/senha → resolve Turnstile via extensão → clica Allow → sign out.

O **Go detecta o token via `PollDevice`** (já existente), salva como conta
normal. Token é JWT OAuth legítimo → funciona nativamente no
`upstream/client.go` (Bearer). **Zero cookie SSO no path de auto-registro.**

```
grok-proxy-plus (Go)                     grok-signup-bot/ (Python, Playwright)
   StartDevice() ────────┐
   verification_uri ─────┼──────────────→ abre URL do device (já com user_code se vier na URI)
   (PollDevice em bg)    │                  ↓ EmailProvider.create_inbox()
                         │                  ↓ signup email + OTP (provider.fetch_code)
                         │                  ↓ nome/senha + Turnstile (extensão)
                         │                  ↓ Complete signup → Continuar → Allow
                         │                  ↓ sign out
   PollDevice() ←────────┘  (token via RFC 8628 — bot NÃO devolve token)
   AccountFromToken() → salva conta → auth:success
```

## Decisões

| Tema | Decisão |
|------|---------|
| **Token** | Device OAuth JWT via `PollDevice` — nunca cookie SSO neste fluxo |
| **Email** | **Agnóstico** — interface `EmailProvider` com backends Mail.tm (default/zero-ops) e DuckMail; fallback em cadeia |
| **Gmail aliases** | Não suportados (xAI rejeita) |
| **Go ↔ Python** | `subprocess` + stdout protocol (`__STEP__` / `__RESULT__`) |
| **Automação** | Playwright (base `qwencloud_full.py`) |
| **Turnstile** | Extensão `turnstile_patch/` (Florisheedless915) |
| **ImportSSO** | **Mantido** como fallback manual + `/v1/sso` |
| **UI de contas** | "Criar conta" é **extra**; **não** remove "Adicionar conta" (device manual) nem "Importar SSO" |

## Email agnóstico (providers + fallback)

### Interface comum

```python
# grok-signup-bot/email_provider.py
from typing import Protocol

class EmailProvider(Protocol):
    name: str  # "mailtm" | "duckmail" | ...

    def create_inbox(self) -> dict:
        """→ {address, id, token, provider}  credenciais para ler OTP."""

    def fetch_code(self, inbox: dict, since_ms: int, timeout: float = 90) -> str | None:
        """Poll até achar código 6 dígitos do xAI; None se timeout."""
```

Regras OTP (iguais para todos):
- Regex `\b\d{6}\b`
- Preferir sender `*@x.ai` ou assunto `verification|verify|code`
- `since_ms` evita código stale

### Backends

| Provider | Módulo | Ops | Notas |
|----------|--------|-----|--------|
| **duckmail** (default) | `email_duckmail.py` | Self-host + `DUCKMAIL_URL` / `DUCKMAIL_KEY` | Mais estável; você controla o servidor |
| **mailtm** (fallback) | `email_mailtm.py` | Zero — API pública `https://api.mail.tm` | Gratuito, pode rate-limit/cair |
| **(futuro)** | `email_*.py` | — | Qualquer API com create + poll encaixa no Protocol |

### Resolução e fallback

Config (Go Settings + env, passados ao bot):

```
email_providers: ["mailtm", "duckmail"]   # ordem de tentativa
duckmail_url / duckmail_key               # só se duckmail estiver na lista
```

No bot:

```python
def create_inbox_with_fallback(providers: list[EmailProvider]) -> dict:
    errors = []
    for p in providers:
        try:
            inbox = p.create_inbox()
            inbox["provider"] = p.name
            return inbox
        except Exception as e:
            errors.append(f"{p.name}: {e}")
            print(f"__STEP__ email_fallback {p.name} failed")
    raise RuntimeError("no email provider worked: " + "; ".join(errors))
```

- **Default MVP:** `["duckmail", "mailtm"]` — tenta DuckMail primeiro, fallback Mail.tm.
- **Sem DuckMail configurado:** só `["mailtm"]` (funciona zero-config).
- Se `create_inbox` ok mas `fetch_code` timeout: **não** trocar de provider no meio do signup (email já foi enviado ao xAI); falhar o fluxo e retry completo com outro provider na próxima tentativa.

## Estrutura de arquivos

```
grok-signup-bot/
├── grok_signup.py              ← automação Playwright
├── email_provider.py           ← Protocol + factory + fallback
├── email_mailtm.py             ← backend Mail.tm (default)
├── email_duckmail.py           ← backend DuckMail
├── turnstile_patch/            ← extensão Chrome
├── requirements.txt            ← playwright
├── run_hidden.sh               ← Xvfb wrapper (opcional)
└── README.md

internal/register/
└── bot.go                      ← Runner: StartDevice + subprocess + progress
```

Frontend: botão + modal em `frontend/src/main.js` (não remove botões existentes).

## Etapa 1 — Providers de email

1. `email_provider.py` — Protocol, factory `build_providers(args)`, fallback
2. `email_mailtm.py` — GET `/domains`, POST `/accounts`, POST `/token`, poll mensagens
3. `email_duckmail.py` — POST mailbox + poll messages (API self-host)

Testáveis isolados (`python -c` / script mínimo) sem browser.

## Etapa 2 — Automação Playwright (`grok_signup.py`)

### Mecanismo de auto-repair

Cada ação crítica usa **múltiplos seletores com fallback** via `or_()`:

```python
from playwright.sync_api import expect

def resolve(locator_builder, page, timeout=10000):
    """Retorna o primeiro locator que encontrar um elemento visível."""
    return expect(locator_builder.first).to_be_visible(timeout=timeout)

# Uso típico:
btn = page.locator("button:has-text('Allow')") \
    .or_(page.locator("[data-testid='allow-btn']")) \
    .or_(page.locator("text=Permitir")) \
    .or_(page.locator("button:has-text('Continuar')"))
btn.first.click(timeout=15000)
```

**Estratégia de fallback por passo:**

| Passo | Seletores primário → fallback |
|-------|--------------------------------|
| Continuar (device) | `text=Continuar`, `button:has-text('Continuar')`, `[data-testid=continue]`, `a:has-text("Continue")` |
| E-mail input | `#email`, `input[name=email]`, `input[type=email]`, `[data-testid=email-input]` |
| Sign up button | `text=Criar conta`, `button:has-text("Sign up")`, `[data-testid=signup-btn]` |
| Nome input | `#name`, `input[name=name]`, `[data-testid=name-input]` |
| Senha input | `#password`, `input[name=password]`, `[data-testid=password-input]` |
| Allow | `text=Allow`, `button:has-text("Permitir")`, `[data-testid=allow]`, `text=Autorizar` |
| Sign out | `text=Sair`, `button:has-text("Sign out")`, `a:has-text("Logout")` |

Se todos os seletores de um passo falharem, o bot captura screenshot + HTML snapshot e aborta com `__RESULT__ {"status":"error","reason":"seletor_quebrado","step":"allow","screenshot":"..."}`.

**Fluxo (device → signup → allow):**
1. `goto(verification_url)` — URL **exata** de `StartDevice` (`verification_uri` /
   `verification_uri_complete` se existir). Se a URI já inclui `user_code`, **não**
   duplicar query params.
2. Continuar (aceitar device) → Sign up
3. Email do provider → Sign up
4. `fetch_code(inbox, since_ms)` → OTP
5. Nome + senha aleatória → Complete signup
6. Turnstile: wait em `cf-turnstile-response` se iframe aparecer (extensão no-op se não houver)
7. Continuar → Allow
8. Success → Sign out (sessão limpa para próxima conta)

**CLI:**

```bash
python3 grok_signup.py \
  --verification-url URL \
  [--user-code CODE] \          # só se a URL não trouxer; informativo/log
  --email-providers mailtm,duckmail \
  [--duckmail-url URL] [--duckmail-key KEY] \
  [--proxy URL] [--headless]
```

**Stdout protocol:**
```
__STEP__ device
__STEP__ email mailtm
__STEP__ otp
__STEP__ profile
__STEP__ turnstile
__STEP__ allow
__STEP__ done
__RESULT__ {"status":"success"}
__RESULT__ {"status":"error","reason":"..."}
```
**Não retorna token.**

## Etapa 3 — Turnstile (`turnstile_patch/`)

- Manifest V3: `challenges.cloudflare.com/*`, `accounts.x.ai/*`
- Patch `MouseEvent.screenX/Y` + click no checkbox do shadow DOM
- Load via `launch_persistent_context` + `--load-extension` / `--disable-extensions-except`
- Só se POC mostrar Turnstile; senão adiar

## Etapa 4 — Ponte Go (`internal/register/bot.go`)

```go
type Progress struct {
    Step    string `json:"step"`    // device|email|otp|profile|turnstile|allow|done|error
    Message string `json:"message"`
}

// CreateAccount:
// 1. ctx, cancel := context.WithTimeout(parent, deviceGrantTTL)  // amarrar bot + poll
// 2. StartDevice(ctx) → verification_uri (+ complete se houver)
// 3. go PollDevice(ctx, device_code, interval)  // mesmo path da main / reutilizar
// 4. exec.CommandContext(ctx, python, script, "--verification-url", uri, ...)
// 5. parse __STEP__/__RESULT__ → emit register:progress
// 6. se bot exit != 0 → cancel()  // interrompe PollDevice
// 7. se poll timeout/denied → kill bot se ainda vivo
// Token só via PollDevice → AccountFromToken → auth:success
```

**Sincronização bot ↔ poll:**
- Um `context` compartilhado com timeout = TTL do device grant (de `StartDevice` / expires_in)
- Falha do bot → cancel poll
- Falha/expiração do poll → cancel subprocess
- Sucesso do poll → pode fechar modal mesmo se bot ainda no sign-out (best-effort)

## Etapa 5 — Frontend

- Botão **"Criar nova conta"** **ao lado** de Adicionar conta / Importar SSO
- Modal de progresso via `register:progress`
- Fecha em `auth:success` (já existe) ou erro + "Tentar novamente"
- Disclaimer ToS no primeiro uso

## Etapa 6 — Wiring `app.go` + Settings

- `register *register.Runner`
- `App.CreateAccount()` + Wails bindings
- Settings (defaults sensatos):

| Campo | Default | Uso |
|-------|---------|-----|
| `python_path` | `python3` | interpretador |
| `bot_dir` | `./grok-signup-bot` (dev) / path empacotado | scripts |
| `email_providers` | `["duckmail", "mailtm"]` | ordem de fallback |
| `duckmail_url` / `duckmail_key` | vazio | se duckmail na lista |

## Diff vs v0

| | v0 | v1 (este) |
|---|---|---|
| Engine | go-rod | Playwright (Python) |
| Email | só Mail.tm | **mailtm + duckmail + pluggable** |
| Token | cookie SSO (quebrado) | Device OAuth JWT |
| Turnstile | JS inject | extensão Chrome |
| UI | substitui botões | **adiciona** botão; mantém device + ImportSSO |
| Fallback SSO | removia no MVP | mantém ImportSSO + `/v1/sso` |

## Pré-requisitos (documentar no README)

- [ ] `python3` + venv
- [ ] `pip install -r grok-signup-bot/requirements.txt`
- [ ] `playwright install chromium`
- [ ] (opcional) DuckMail up + URL/key se não for só mailtm
- [ ] (Linux headless) Xvfb se usar `run_hidden.sh`

## Ordem de implementação

1. `email_provider.py` + `email_mailtm.py` (testar create + OTP real com xAI se possível)
2. `email_duckmail.py` (opcional no MVP; interface já pronta)
3. `grok_signup.py` POC com `--verification-url` de um `StartDevice` real
4. `turnstile_patch/` se necessário
5. `internal/register/bot.go` (ctx compartilhado, timeout, cancel cruzado)
6. `App.CreateAccount` + bindings
7. Frontend modal (sem remover botões existentes)
8. Docs: marcar v0 obsoleto; atualizar `grok-register-analysis.md`

## Riscos

| Risco | Mitigação |
|-------|-----------|
| Seletores accounts.x.ai | POC manual antes de empacotar |
| Mail.tm instável | Fallback para duckmail; retry create_inbox |
| OTP timeout no meio do fluxo | Falha limpa + retry completo (não mid-switch de email) |
| Turnstile | Extensão; no-op se ausente |
| Python no Wails | Docs + settings path; bundle depois |
| Race bot vs PollDevice | ctx + timeout + cancel cruzado |
| ToS | Disclaimer no 1º uso |

## Estimativa

| Etapa | Esforço |
|-------|---------|
| Email Protocol + mailtm | 2h |
| email_duckmail | 1h |
| grok_signup.py POC + seletores | 4–6h |
| Turnstile patch | 0–2h |
| bot.go (ctx/timeout/cancel) | 2–3h |
| App + bindings | 1h |
| Frontend modal | 2h |
| Docs | 1h |
| **Total** | **13–18h** |

## Status (2026-07-09)

| Etapa | Status | Arquivos |
|-------|--------|----------|
| 1 — Email providers | ✅ Feito | `email_provider.py`, `email_mailtm.py`, `email_duckmail.py` |
| 2 — grok_signup.py | ✅ Feito | `grok_signup.py` |
| 3 — Turnstile patch | ⏸️ Adiado (não há iframe visível no POC) | — |
| 4 — bot.go (Go bridge) | ✅ Feito | `internal/register/bot.go` |
| 5 — App.CreateAccount | ✅ Feito | `app.go` |
| 6 — Frontend modal | ✅ Feito | `frontend/src/main.js` (botão + modal) |
| Dead code cleanup | ✅ Feito | `nextAvailableAccount()` removido de `server.go` |
| DuckMail default | ✅ Feito | `email_provider.py` default providers = `["duckmail", "mailtm"]` |

## Checklist

- [x] `EmailProvider` + factory + fallback
- [x] mailtm default; duckmail opcional
- [ ] verification_uri de `StartDevice` sem duplicar user_code (pendente POC real)
- [ ] Bot e PollDevice no mesmo ctx/timeout; cancel cruzado (pendente POC real)
- [x] Bot não devolve token
- [x] ImportSSO e device manual permanecem
- [x] "Criar conta" é botão adicional
- [ ] Settings: python_path, bot_dir, email_providers, duckmail_* (pendente — usar env por ora)
- [ ] Pré-reqs no README
