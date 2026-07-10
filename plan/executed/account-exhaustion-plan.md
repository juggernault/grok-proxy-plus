# Plano: Detecção de Erros do Upstream + Auto-Switch + Notificação ao OpenCode

> Achados: [`FINDINGS.md`](./FINDINGS.md) · Residual UI/usage: [`hardening-plan-v1.md`](./hardening-plan-v1.md) **Fase B**

## Status atual (2026-07-09) — sync com código

### Feito (stable)

| O que | Status | Onde |
|-------|--------|------|
| Logging + `diagnoseUpstreamError()` | ✅ | `proxyhttp/server.go` |
| Header `X-Account-Status` = classification | ✅ | proxy + anthropic |
| `Account.Exhausted` / `ExhaustedAt` | ✅ | `store/store.go` |
| `IsExhausted()` (janela **24h**), mark/reset/recover | ✅ | store |
| `PublicAccounts` → exhausted efetivo + status | ✅ | store |
| Mark em `rate_limit` (429/402) | ✅ | `proxyUpstream`, `handleMessages` |
| `ensureCreds` pula exausta/expired + refresh + rotate | ✅ | `app.go` |
| Retry same-request c/ `tried` + body buffer (até 5) | ✅ | `server.go`, `anthropic.go` |
| `X-Account-Status: all-exhausted` | ✅ | proxy |
| `recordUsage` com **`pricing.CostUSD` + model real** | ✅ | `server.go` |
| SSE keep-last-nonzero usage | ✅ | `sse.go` |
| Merge `include_usage: true` | ✅ | `enrichBody()` |
| Timer UI 60s + badge/Resetar | ✅ | `frontend/src/main.js` |
| `ResetAccount` / `RecoverAccounts` | ✅ | `app.go` |

### Residual

| O que | Status | ID |
|-------|--------|-----|
| `usage:update` / `accounts:update` a partir do proxy | ✅ | H4 |
| Desktop `SendChat` marca exaustão em rate limit | ✅ | H6 |
| UI card live (paintChrome em usage:update) | ✅ | H4 |
| Anthropic grava usage no sucesso | ✅ | H7 |
| Testes diagnose + recordUsage hook | ✅ | H13 parcial |
| Teste e2e failover 429 A→200 B (mock transport) | ✅ `failover_test.go` | |

### Comportamento atual (failover proxy)

```
OpenCode → POST /v1/* → Proxy → cli-chat-proxy
                              ↓ 429 rate_limit
           MarkAccountExhausted + tried → ensureCreds → re-Do
                              ↓ 200
OpenCode ← 200 (usage com CostUSD + model)
X-Account-Status: rate_limit | all-exhausted | ...
```

---

## Usage / card vs OpenCode

| Path | Grava usage | CostUSD | Evento UI |
|------|-------------|---------|-----------|
| Desktop `SendChat` | ✅ | ✅ | ✅ `usage:update` + `stats:sample` |
| Proxy `proxyUpstream` | ✅ `recordUsage` | ✅ **CostUSD** | ✅ OnUsage → usage:update |

Proxy **já persiste** custo; UI de cards só atualiza em bootstrap / `accounts:update` / timer 60s.

### Bugs corrigidos

- CostUSD 0 + model=path → fix em `recordUsage`
- SSE zero overwrite → keep-last-nonzero
- `include_usage` merge
- Recover logo após mark removido

### Aberto (ver hardening B1–B4)

- OnUsage callback no Server → EventsEmit
- Anthropic `recordUsage` no sucesso
- Desktop mark em rate limit
- Frontend: `usage:update` → `paintChrome()` nos cards

### Fluxo alvo

```
OpenCode → stream → recordUsage → OnUsage → usage:update + accounts:update → paintChrome
```

---

## Regras

- Só mark em `classification == "rate_limit"` (429/402)
- Janela `IsExhausted` = **24h**
- Retry só pre-stream; `tried` por request

## Checklist residual

- [x] OnUsage → emits do proxy
- [x] Anthropic usage
- [x] Desktop mark rate limit
- [x] Frontend repinta cards em usage:update
- [x] Testes unitários usage/diagnose
- [x] Teste e2e failover 429 A→200 B (mock)

**Fase B hardening: concluída.**
