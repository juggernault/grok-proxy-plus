# Achados de auditoria — Grok Proxy Plus

> Snapshot: **2026-07-09**. Hardening A–C aplicado no código (ver `hardening-plan-v1.md`). Base: código em `app.go`, `internal/*`, `frontend/`, `grok-signup-bot/`.  
> Docs: `README.md`, `grok-signup-bot/README.md`, `docs/grok-register-analysis.md`.  
> Planos concluídos: este dir. Residual: [`../open/hardening-plan-v1.md`](../open/hardening-plan-v1.md).

## 1. Mapa do que está implementado

| Área | Estado | Onde |
|------|--------|------|
| OAuth device + refresh multi-conta | ✅ | `oauth/`, `app.go` StartDeviceLogin |
| Proxy OpenAI chat/responses + models | ✅ | `proxyhttp/server.go` |
| Proxy Anthropic `/v1/messages` | ✅ retry; ⚠️ usage | `proxyhttp/anthropic.go` |
| Stream thinking + tools + search UI | ✅ | `upstream/`, `app.go` SendChat |
| Pricing / stats / snippets OpenCode | ✅ | `pricing/`, GetStats |
| Exhaustion 24h + proxy same-request failover | ✅ | store + proxyUpstream |
| SSO paste / file / sso-watch / POST /v1/sso | ✅ | app.go, proxyhttp |
| Auto-register bot + batch + loop 5min | ✅ frágil packaging | register/, grok-signup-bot/, app.go |
| Skills store + inject prompt | ⚠️ sem UI | skills/, injectAgentContext |
| MCP config JSON + inject prompt | ⚠️ sem bridge | mcpconfig/ |

## 2. Gaps documentação (já mitigados nesta auditoria)

| Antes | Depois |
|-------|--------|
| README sem SSO / auto-register / register|skills|mcpconfig | README atualizado |
| Bot README “Phase A only” | README bot = DrissionPage + protocolo |
| Exhaustion plan dizia CostUSD:0 no proxy | Corrigido: CostUSD ✅; UI live ainda ❌ |
| Auto-register plan Playwright | Nota DrissionPage + checklist real |

## 3. Problemas (bugs / riscos)

### P0 — correção recomendada

| ID | Problema | Evidência | Impacto |
|----|----------|-----------|---------|
| **H1** | Auto-register grava token via `ImportSSO` (exp 90d, **sem refresh_token**) | `CreateAccountFromDevice` → `ImportSSO` | Contas auto morrem sem refresh OAuth |
| **H2** | Paths Python/bot hardcoded `exe/../../.venv` + `../../grok-signup-bot` | `app.go` startup | Release binary: auto-register quebra |
| **H3** | `autoRegisterLoop` **sempre** ativo se &lt;2 contas | `startup` → `go autoRegisterLoop()` | Browser/ToS/flood sem consentimento |
| **H4** | Proxy grava usage com CostUSD mas **não** emite eventos UI | `recordUsage` sem hook App | Card conta desatualizado no OpenCode até poll 60s |

### P1 — qualidade / consistência

| ID | Problema | Evidência |
|----|----------|-----------|
| **H5** | `SendChat` força `req.APIMode = "responses"` | app.go ~814; chip UI/settings ignorados |
| **H6** | Desktop não `MarkAccountExhausted` em rate limit | só proxy path |
| **H7** | Anthropic sucesso não chama `recordUsage` | anthropic.go |
| **H8** | `sso-watch` `seen` só por filename | re-drop/edit não reimporta |
| **H9** | `CreateAccount(url,code)` só roda bot (sem poll) | fácil de misusar vs FromDevice |
| **H10** | Bot/poll timeouts separados (240s / 60s), sem cancel cruzado forte | CreateAccountFromDevice |

### P2 — produto incompleto / dívida

| ID | Problema |
|----|----------|
| **H11** | Skills/MCP no bootstrap sem UI e sem execução MCP |
| **H12** | `frontend/src/main.js` monólito (~1.6k linhas) |
| **H13** | Poucos testes (só `tools_test.go` relevante no proxy) |
| **H14** | UI/erros PT vs README EN |
| **H15** | Tokens/SSO plaintext em AppData; `/v1/sso` aberto se API key vazia |

## 4. Melhorias (sem ser bug)

1. Settings: `python_path`, `bot_dir`, `email_providers`, `auto_register_enabled` (default **false**).
2. `OnUsage` / `OnAccountsChanged` no `proxyhttp.Server` wired no `App`.
3. Frontend: `usage:update` → atualizar `state.usage` **e** `paintChrome()` cards.
4. Pós-PollDevice: `oauth.AccountFromToken` + UserInfo + Upsert (igual device login manual).
5. Eventos `register:progress` para modal de batch.
6. Modularizar frontend (accounts, chat, stats, register).
7. Testes: store IsExhausted, ensureCreds rotation, failover 429, recordUsage CostUSD.
8. Documentar pré-reqs auto-register no release notes.

## 5. O que **não** abrir como bug

- Failover same-request no proxy OpenAI/Anthropic: **feito**.
- CostUSD no path proxy OpenAI: **feito** (persistência ok; falta UI live).
- Device login manual com refresh: **ok** (`AccountFromToken`).
- Disclaimer / ToS risk: esperado; manter DISCLAIMER.

## 6. Planos relacionados

| Doc | Escopo |
|-----|--------|
| [`account-exhaustion-plan.md`](./account-exhaustion-plan.md) | Failover + usage card |
| [`auto-register-plan-v1.md`](./auto-register-plan-v1.md) | Bot + batch + loop |
| [`hardening-plan-v1.md`](./hardening-plan-v1.md) | **Novo** — fechar H1–H15 em fases |
| [`grok-register-analysis.md`](../../docs/grok-register-analysis.md) | Guia prático SSO (usuário) |

## 7. Ordem sugerida de execução

Ver **hardening-plan-v1** fases A→D. Resumo:

1. **A** Token + gate auto-register + settings paths  
2. **B** OnUsage + Anthropic usage + desktop mark + UI cards  
3. **C** API mode honor + sso-watch mtime + register progress  
4. **D** Skills/MCP + frontend split → residual em `plan/open`  


## 8. Status pós-hardening (código)

| ID | Status |
|----|--------|
| H1 AccountFromToken | ✅ `CreateAccountFromDevice` |
| H2 paths settings | ✅ `python_path` / `bot_dir` + resolve |
| H3 loop default off | ✅ `auto_register_enabled` default false |
| H4 OnUsage proxy | ✅ + frontend `paintChrome` |
| H5 API mode | ✅ honra settings/request |
| H6 desktop mark | ✅ `isRateLimitErr` |
| H7 Anthropic usage | ✅ stream + non-stream |
| H8 sso-watch mtime | ✅ |
| H9 CreateAccount bot-only | ✅ documentado; UI usa CreateAccounts |
| H10 shared ctx | ✅ timeout 300s compartilhado |
| H11 Skills/MCP UI | ✅ cut claim (option Y); store only
| H13 testes unitários | ✅ store + proxy + failover
| H14 i18n | ✅ PT-BR UI documentado no README
| H15 plaintext tokens | ⬜ aceito (não-plano)
| H12 frontend split | ✅ modules under frontend/src/ |

| Email providers/DuckMail → bot args | ✅ register.Runner + grok_signup.py |
