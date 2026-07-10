# Plano: Auto-registro de conta xAI via Device Login + bot

> Substitui o plano v0 (`auto-register-plan-v0.md-deprecated`). Cookie SSO não
> funciona como Bearer no upstream. Este fluxo usa **Device Login OAuth**.
>
> Achados gerais: [`FINDINGS.md`](./FINDINGS.md) · Hardening residual: [`hardening-plan-v1.md`](./hardening-plan-v1.md)

## Visão geral

Go dispara Device Login → passa **verification URL** ao bot Python → bot faz
signup com email temp → Go **PollDevice** obtém JWT → salva conta.

```
grok-proxy-plus (Go)                     grok-signup-bot/ (Python)
   StartDevice() ────────┐
   verification_uri ─────┼──────────────→ DrissionPage + email providers
   PollDevice() ←────────┘
   ImportSSO(access) → auth:success   ← ⚠️ FINDINGS H1: trocar por AccountFromToken
```

> **Implementação:** plano original citava Playwright; código usa **DrissionPage**
> (`grok_signup.py`, `requirements.txt`). `turnstilePatch/` presente; Turnstile
> marcado adiado se não houver iframe.

## Decisões

| Tema | Decisão |
|------|---------|
| Token | Device OAuth via `PollDevice` |
| Email | DuckMail + Mail.tm (fallback só create_inbox) |
| Browser | **DrissionPage** |
| Go ↔ Python | subprocess + `__STEP__` / `__CREDS__` / `__RESULT__` |
| SSO manual | Mantido (UI, file, sso-watch, `/v1/sso`) |
| UI | "+ Gerar contas" extra; device + Import SSO permanecem |

## Arquivos reais

```
grok-signup-bot/
├── grok_signup.py, email_*.py, creds.py, turnstilePatch/, requirements.txt
internal/register/bot.go
app.go  # CreateAccount*, autoRegisterLoop, CreateAccounts
```

## Protocolo stdout

```
__STEP__ <step>
__CREDS__ {"email","name","password","provider"}
__RESULT__ {"status":"success|error","reason":"..."}
```

Bot **não** devolve token OAuth.

## Features implementadas

| Feature | Onde |
|---------|------|
| Email providers + fallback | `email_provider.py` |
| Signup automation | `grok_signup.py` (DrissionPage) |
| Creds / auto_creds.json | `creds.py` + Runner.CredsDir |
| Go bridge | `internal/register/bot.go` |
| `CreateAccountFromDevice` | StartDevice → bot → PollDevice → ImportSSO |
| `CreateAccounts(n)` max 5 | app.go + UI |
| `autoRegisterLoop` 5 min, alvo ≥2 | app.go (sempre on no startup) |

## Status (2026-07-09)

| Item | Status |
|------|--------|
| Email + bot + bridge + UI batch | ✅ |
| Turnstile | ⏸️ adiado / patch presente |
| Settings python_path / bot_dir / providers | ✅ settings + resolve |
| Bot + poll mesmo ctx / cancel cruzado | ✅ ctx 300s compartilhado |
| AccountFromToken + refresh_token | ✅ |
| Gate off para autoRegisterLoop | ✅ default off |
| Docs README + bot README | ✅ |

## Checklist pendente

- [x] Settings configuráveis (python/bot/providers)
- [ ] Packaging release (bundle python ainda manual)
- [x] PollDevice → `AccountFromToken` (não ImportSSO)
- [x] Setting `auto_register_enabled` default **off**
- [x] Eventos `register:progress` para UI

## Riscos

ToS/ban, path Python em release, token sem refresh, loop sempre ativo, seletores xAI.

## Diff vs v0

| | v0 | v1 |
|---|---|---|
| Engine | go-rod | DrissionPage (plano: Playwright) |
| Token | cookie SSO | Device OAuth JWT |
| Email | só Mail.tm | pluggable + fallback |
