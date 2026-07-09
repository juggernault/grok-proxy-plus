# Plano: Detecção de Erros do Upstream + Auto-Switch + Notificação ao OpenCode

## Status atual (2026-07-09)

### Feito (stable)

| O que | Status | Onde |
|-------|--------|------|
| Logging + `diagnoseUpstreamError()` | ✅ | `proxyhttp/server.go` |
| Header `X-Account-Status` = classification | ✅ | proxy + anthropic |
| `Account.Exhausted` / `ExhaustedAt` | ✅ | `store/store.go` |
| `IsExhausted()` (janela **24h**), `MarkAccountExhausted()`, `ResetAccountExhausted()`, `RecoverExhaustedAccounts()` | ✅ | store |
| `PublicAccounts` expõe `exhausted` + `exhausted_status` | ✅ | flag raw + status string ("exausta" / "recuperada" / "") |
| Mark em `rate_limit` (429/402) | ✅ | `proxyUpstream`, `handleMessages` |
| `ensureCreds` pula conta exausta + recover lazy no início | ✅ | `app.go` |
| `ensureCreds` pula conta `expired` também e tenta refresh OAuth | ✅ | app.go — se refresh falhar, pula p/ próxima (até 3 tentativas) |
| `ensureCreds` valida `IsExhausted()` no retorno (evita devolver conta exausta) | ✅ | app.go |
| `ensureCreds` troca ActiveAccount + emite `accounts:update` | ✅ | app.go + frontend `wireEvents` |
| `ensureCreds` valida `acc.IsExhausted()` no retorno | ✅ | app.go — retorna erro se só sobrarem exaustas |
| Timer periódico 60s (RecoverAccounts + GetBootstrap + paintChrome) | ✅ | frontend `main.js` `setInterval` |
| Meta-line com `flex-wrap` (evita scroll horizontal no card) | ✅ | `style.css` |
| Conta expirada **não é removida** — só pulada | ✅ | app.go |
| `ResetAccount` / `RecoverAccounts` bindings Wails | ✅ | app.go + frontend |
| Badge "exausta" + botão "Resetar" no card | ✅ | frontend |
| Retry same-request c/ `tried` set + loop (proxyUpstream) | ✅ | `proxyhttp/server.go` — até 5 tentativas, body buffer |
| Retry same-request c/ `tried` set + loop (anthropic) | ✅ | `internal/proxyhttp/anthropic.go` |
| Header `X-Account-Status: all-exhausted` quando todas exaustas | ✅ | `proxyUpstream` |
| `enrichBody()` fatorada (evita duplicação body enrichment entre retries) | ✅ | `proxyhttp/server.go` |
| `recordUsage` com `pricing.CostUSD` + model real (não path) | ✅ | `proxyhttp/server.go` |
| SSE keep-last-nonzero usage (não sobrescreve com zero) | ✅ | `internal/proxyhttp/sse.go` |
| Forçar merge `include_usage: true` mesmo se `stream_options` já existe | ✅ | `enrichBody()` → merge no map |
| `PublicAccounts` com `a.IsExhausted()` (efetivo, não flag raw) | ✅ | `store/store.go` |
| Parsing de usage no proxy (SSE/JSON) com CostUSD real | ✅ | `proxyhttp/server.go` + `sse.go` |
| `nextAvailableAccount()` definida | ✅ | `proxyhttp/server.go` — **não usada** (dead code) |
| `nextNonExhaustedWithContext()` | ✅ | app.go — usada no loop de refresh |
| RecoverExhaustedAccounts no ensureCreds | ✅ | desbloqueia contas após 24h |

### **Não** feito

| O que | Status |
|-------|--------|
| nextAvailableAccount() ainda dead code | ❌ (remover ou usar) |
| Evento Wails `accounts:update` no mark/switch | ✅ | app.go `emitAccountsUpdate` + frontend `paintChrome` |
| Desktop path (`app.go SendChat`) marca exaustão em rate limit | ❌ |
| UI live no card (OnUsage → EventsEmit → paintChrome) | ❌ |

### Comportamento atual (failover invisível ativo):

```
OpenCode → POST /v1/chat/completions → Proxy → cli-chat-proxy
                                         ↓ 429 rate_limit
                      MarkAccountExhausted + tried
                      next loop iteration: ensureCreds + re-Do body buffer
                                         ↓ 200
OpenCode ← 200 (usage gravado com CostUSD real + model real)

Todas exaustas:
OpenCode ← 429 + X-Account-Status: all-exhausted
```

---

## Usage / custo no card vs agent harness (OpenCode)

### Sintoma

Ao usar **OpenCode** (ou outro cliente no proxy local), o **card da conta** (tok / $ / req) **não reflete** o gasto em tempo real — ou fica $0 / defasado vs o que o harness e o free tier xAI realmente consumiram.

### Dois caminhos de telemetria (assimetria)

| Path | Quem grava usage | CostUSD | Evento UI |
|------|------------------|---------|-----------|
| **Desktop chat** `App.SendChat` → `upstream.StreamChat` | `app.go` em `ev.type == "usage"` | ✅ `pricing.CostUSD(...)` | ✅ `usage:update` + `stats:sample` |
| **Proxy** OpenCode/etc → `proxyUpstream` | `recordUsage()` | ❌ **sempre `CostUSD: 0`** | ❌ **nenhum** evento Wails |

O card lê `a.usage` de `PublicAccounts()` (snapshot do store). Sem `RecordRequest` correto **e** sem refresh da UI, o card mente.

### Bugs já corrigidos

| Bug | Fix | Onde |
|-----|-----|------|
| CostUSD: 0 + model = path no proxy | `recordUsage` usa `pricing.CostUSD` + model real do body | `server.go` |
| SSE overwrite usage com zero | Keep-last-nonzero: só atualiza se >0 | `sse.go` |
| `include_usage` não forçado se `stream_options` existia | Merge: `include_usage: true` sempre | `enrichBody()` |
| `RecoverExhaustedAccounts()` chamado imediatamente após mark | Removido do path de erro | `server.go` |

### Bugs ainda abertos

#### UI não reage a usage do proxy

- `EventsOn("usage:update")` só atualiza KPIs **globais** — não chama `paintChrome()`.
- Proxy **nunca** emite `usage:update` (Server não tem hook de App).
- Card muda só em `refreshBootstrap` (login, select, reset, boot).

#### Anthropic path não grava usage

- `handleMessages` não chama `recordUsage` no sucesso.
- Card não reflete gasto de clientes Anthropic-compatible.

#### 7. OpenCode “contador de tokens” (validação)

| Pergunta | Resposta |
|----------|----------|
| OpenCode **envia** tokens no request? | **Não** — o client não “posta” usage; o **upstream** devolve usage no response/SSE. |
| Proxy pede usage? | Tenta via `stream_options.include_usage` (com o buraco do §5). |
| OpenCode UI de tokens | Conta o que **recebe** do stream (usage final / estimativa local). Independente do card Grok Desktop. |
| Dados “corretos” no OpenCode | Depende do upstream devolver `usage` no último chunk; se proxy strip/não pedir, OpenCode também subconta. **Não validamos o binário OpenCode aqui** — o contrato OpenAI é: client pede `include_usage`, provider devolve `usage`. |

**Conclusão validação OpenCode:** o harness **não é a fonte** do card. O card depende do **proxy** parsear o usage do **cli-chat-proxy** e persistir. Se o card está errado, o bug é nosso (1–6), não “OpenCode não manda tokens”.

### Fluxo alvo (usage agent harness)

```
OpenCode → stream chat/completions (+ include_usage forçado)
         → Proxy pipeSSEWithUsage (keep last non-zero usage)
         → recordUsage(accountID, modelFromBody, tokens, pricing.CostUSD)
         → store.RecordRequest
         → onUsage callback → EventsEmit("usage:update") + "accounts:update"
         → Frontend: state.usage + refresh accounts / paintChrome
Card tok/$/req sobe em live
```

### Trabalho usage (prioridade)

#### U0 — Custo e model no `recordUsage` ✅

- [x] `CostUSD: pricing.CostUSD(model, prompt, completion, reasoning, cached)`
- [x] `Model:` id real do body (fallback settings.DefaultModel), **não** path
- [ ] Opcional: `CachedTokens` se o payload trouxer `prompt_tokens_details.cached_tokens`

#### U1 — Captura SSE robusta ✅

- [x] Não sobrescrever usage bom com zero (keep-last-nonzero)
- [x] Merge `include_usage: true` em `stream_options` existente
- [ ] Log debug quando stream termina com usage==0 (para distinguir “upstream não mandou” vs bug parse)

#### U2 — UI live no card

- [ ] Callback no `Server` (ex. `OnUsage func(store.RequestSample)`) registrado em `app` startup
- [ ] Emit `usage:update` do proxy path (Server não tem hook de App)
- [ ] Frontend: em `accounts:update`, `paintChrome()` já repinta cards incluindo usage
- [ ] Anthropic path: gravar usage no sucesso (mapear tokens OpenAI→sample)

#### U3 — Validação manual / testes

- [ ] Request curl stream com `include_usage` → history com CostUSD > 0
- [ ] OpenCode turn → card sobe sem reiniciar app
- [ ] Comparar total store vs mensagem free-usage-exhausted (~1M) após sessão longa (sanity)

---

## Contexto de produto / diagnóstico

1. Upstream = `cli-chat-proxy.grok.com` (não API xAI “pública” direta).
2. Rate limit real observado: `subscription:free-usage-exhausted` (~1M tok/24h).
3. Dual path: Desktop UI `/responses` vs OpenCode `/chat/completions`.
4. Classificações: `rate_limit` | `client_version` | `auth_error` | `invalid_request` | `server_error` | `unknown`.

Só **`rate_limit` (429/402)** marca conta. Nunca exhaust em version/auth/invalid/server.

---

## Regras de design (obrigatórias)

| Regra | Motivo | Código hoje |
|-------|--------|-------------|
| Só mark em `classification == "rate_limit"` | 403 ≠ quota | ✅ |
| Capturar `acc` do `ensure` | mark no ID certo | ✅ |
| Retry com body em memória + `NewRequest` | Body consumido | ✅ loop no proxyUpstream |
| Switch via `SetActiveAccount` + `ensure` (refresh) | Token fresco | ✅ (ensureCreds no loop) |
| `tried` map por request | Evita loop infinito | ✅ |
| Failover só pre-stream | SSE já aberto | ✅ (só retry antes de enviar SSE) |
| Gate só `IsExhausted()` | Janela temporal | ✅ |
| `PublicAccounts` → status **efetivo** | UI não mente após recover | ✅ `a.IsExhausted()` |
| Header `all-exhausted` quando nenhuma sobra | Distinto de rate_limit | ✅ server.go |
| Evento Wails no mark | UI sem poll | ❌ |
| Proxy grava usage **com custo** + model real | Card reflete agent harness | ✅ |
| UI reage a usage do proxy | Card live | ❌ |

### Janela de auto-recover

| | Plano original | Código atual |
|--|----------------|--------------|
| `IsExhausted` | 1 hour | **24 hours** (`store.go`) |

**Decisão documentada:** manter **24h** alinhado ao reset de quota free (~1M/24h). Se rate limit for mais curto no futuro, tornar configurável. Não misturar 1h no doc com 24h no código.

---

## Trabalho restante (prioridade)

### P0 — Retry same-request (objetivo original failover)

Em `proxyUpstream` e `handleMessages`, quando `rate_limit`:

1. `MarkAccountExhausted(acc.ID)`
2. `tried[acc.ID] = true`
3. `nextID := nextAvailableAccount(...)` **excluindo tried**
4. Se vazio → `X-Account-Status: all-exhausted`, devolver erro
5. Senão `SetActiveAccount` + `token, acc, settings = ensure(ctx)`
6. Recriar request: `bytes.NewReader(body)` + headers + `Do`
7. Max tentativas = min(5, nº contas)

### P0b — Usage/custo agent harness (card)

Ver § Usage: U0 + U1 + U2 (custo, captura, eventos UI). Pode ser **paralelo** ao failover e é o que o usuário sente no card ao usar OpenCode.

### P1 — Consistência store/API/UI

- [ ] `PublicAccounts`: `"exhausted": a.IsExhausted()` (efetivo)
- [ ] Opcional: `"exhausted_at"`
- [ ] Remover ou **usar** `nextAvailableAccount` no retry
- [ ] Não `RecoverExhaustedAccounts()` logo após mark

### P2 — Eventos e header (failover + usage)

- [ ] `X-Account-Status: all-exhausted`
- [ ] Hook App no `Server` para `accounts:update` / `accounts:exhausted` / `usage:update`

### P3 — Hardening

- [ ] tried-set + logs
- [ ] Teste 429 A → 200 B same-request
- [ ] Teste usage stream → CostUSD > 0 + card
- [ ] Desktop path: mark em rate limit se aplicável

---

## Fluxo alvo (failover, quando P0 existir)

```
OpenCode → POST /v1/chat/completions → Proxy → cli-chat-proxy
                                         ↓ 429 rate_limit
                      MarkAccountExhausted + tried
                      SetActiveAccount(next) + ensure(refresh)
                      re-Do body buffer
                                         ↓ 200
OpenCode ← 200 (+ usage gravado com custo)

Todas exaustas:
OpenCode ← 429 + X-Account-Status: all-exhausted
Frontend ← accounts:exhausted (se P2)
```

---

## Arquivos

| Arquivo | Status | Notas |
|---------|-------|-------|
| `internal/store/store.go` | ✅ | PublicAccounts com IsExhausted() |
| `internal/proxyhttp/server.go` | ✅ | Retry loop + recordUsage com CostUSD+model + all-exhausted |
| `internal/proxyhttp/anthropic.go` | ✅ | Retry loop; sem recordUsage no sucesso |
| `internal/proxyhttp/sse.go` | ✅ | Keep-last-nonzero usage |
| `internal/proxyhttp/tools.go` | ✅ | asInt64 usado no sse |
| `internal/pricing/pricing.go` | ✅ | CostUSD usado no proxy |
| `app.go` | ⚠️ | ensureCreds ok; falta wire OnUsage → EventsEmit |
| `frontend/src/main.js` | ⚠️ | usage:update não repinta cards de conta |

---

## Checklist

### Feito
- [x] Classificação + log de erro upstream
- [x] Mark em rate_limit
- [x] Campos + IsExhausted (janela **24h**)
- [x] ensureCreds pula exausta + expired + refresh OAuth
- [x] ResetAccount + RecoverAccounts + UI badge/reset
- [x] Retry same-request c/ `tried` set + body buffer (proxyUpstream + anthropic)
- [x] Header `X-Account-Status: all-exhausted`
- [x] recordUsage com `pricing.CostUSD` + model real
- [x] SSE keep-last-nonzero usage
- [x] Forçar `include_usage: true` mesmo se stream_options existe
- [x] PublicAccounts com `a.IsExhausted()` efetivo
- [x] Removido `RecoverExhaustedAccounts()` imediatamente após mark

### Pendente
- [ ] nextAvailableAccount() — remover ou usar (dead code)
- [ ] Anthropic path grava usage no sucesso
- [ ] OnUsage callback no Server → `usage:update` do proxy (hoje só do desktop chat)
- [ ] Testes de failover (429 A → 200 B same-request)
- [ ] Validar curl stream → history com CostUSD > 0

---

## Estimativa residual (atualizada)

| Etapa | Esforço |
|-------|---------|
| OnUsage callback + EventsEmit + frontend paint cards | 1–2h |
| Anthropic path gravar usage | 0.5h |
| Limpeza dead code nextAvailableAccount | 0.2h |
| Testes (failover + usage) | 1–2h |
| **Total residual** | **~3–5h** |
