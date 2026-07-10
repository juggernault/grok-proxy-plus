# Plano v1 — Hardening residual (pós-auditoria 2026-07-09)

> **Status pasta:** `plan/open` — **não** está 100% executado.  
> **Já feito (código):** Fases A, B, C e D parcial (testes + decisão Skills/MCP backend-only).  
> Histórico completo e checklists de A–C: ver também `plan/executed/FINDINGS.md` §8.


## Princípios

1. **Não quebrar** path device login manual nem proxy OpenCode.
2. Auto-register **opt-in** (default off).
3. Tokens de device poll sempre com **refresh** quando o grant trouxer.
4. Proxy e desktop devem **convergir** em mark exhaustion + telemetria UI.
5. Cada fase = commits pequenos e verificáveis.

---

## Fase A — Auto-register seguro (P0)

**IDs:** H1, H2, H3, H10 (parcial)

### A1. PollDevice → AccountFromToken (não ImportSSO)

Em `CreateAccountFromDevice` (após `PollDevice` ok):

```go
acc := oauth.AccountFromToken(tok, a.oauth.ClientID, a.oauth.Issuer)
// UserInfo email/uid como em StartDeviceLogin
// UpsertAccount + SetActiveAccount + auth:success
```

- Manter `ImportSSO` só para tokens SSO verdadeiros / import manual / `/v1/sso`.
- Critério: conta auto-criada tem `RefreshToken` quando o token response incluir.

### A2. Settings + paths

Estender `store.Settings` (defaults sensatos):

| Campo | Default | Uso |
|-------|---------|-----|
| `auto_register_enabled` | **false** | gate do loop |
| `auto_register_min_active` | 2 | alvo do loop |
| `auto_register_max_active` | 5 | max por lote/onda (não pool) |
| `python_path` | `python3` ou detect | Runner |
| `bot_dir` | vazio → resolve ao lado do exe / env | Runner |
| `email_providers` | `["mailtm"]` | repassar ao bot |
| `duckmail_url` / `duckmail_key` | "" | env/args bot |

`startup`:

- `register.New(settings.PythonPath, settings.BotDir)` com fallbacks documentados.
- `go autoRegisterLoop()` **só se** `auto_register_enabled`.

### A3. Loop e batch respeitam setting

- `autoRegisterLoop` e UI “Gerar contas” checam flag (UI pode forçar batch mesmo com loop off).
- Log claro se python/bot path inválido.

### A4. Ctx compartilhado (melhoria)

- Um `context.WithTimeout` amarrado a `expires_in` do device grant.
- Cancel bot se poll falhar e vice-versa (best-effort).

**Done quando:** release com venv embutido ou path em settings cria conta com refresh; app sem flag não abre browser sozinho.

**Estimativa:** 3–5h

---

## Fase B — Telemetria e exhaustion paridade (P0/P1)

**IDs:** H4, H6, H7 (+ residual exhaustion plan U2)

### B1. Hook no Server

```go
// proxyhttp.Server
OnUsage func(sample store.RequestSample)
OnAccountChange func() // após mark / switch
```

Em `app.startup` ao criar proxy:

```go
a.proxy.OnUsage = func(s store.RequestSample) {
  runtime.EventsEmit(a.ctx, "usage:update", a.store.UsageSnapshot())
  runtime.EventsEmit(a.ctx, "stats:sample", s)
  a.emitAccountsUpdate()
}
a.proxy.OnAccountChange = a.emitAccountsUpdate
```

Chamar após `recordUsage` e após `MarkAccountExhausted` / rotate.

### B2. Anthropic `recordUsage` no sucesso

Espelhar parsing de tokens do path OpenAI (ou mapear usage Anthropic → sample).

### B3. Desktop mark

Em `SendChat`, se `StreamEvent` error classificar como rate_limit (ou string match free-usage-exhausted):

- `MarkAccountExhausted(acc.ID)`
- `emitAccountsUpdate`
- opcional: retry uma vez com `ensureCreds` (pode ficar P2)

### B4. Frontend

- Em `usage:update`: atualizar state **e** `paintChrome()` (cards tok/$).
- Garantir que `accounts:update` já repinta (validar).

**Done quando:** OpenCode stream → card sobe em &lt;2s sem timer 60s; Anthropic usage no history; desktop rate-limit marca badge.

**Estimativa:** 2–4h

---

## Fase C — Consistência UX / SSO (P1)

**IDs:** H5, H8, H9

### C1. API mode

- Remover force `req.APIMode = "responses"` **ou**
- Documentar “desktop always Responses” e esconder chip enganoso.
- Preferência: honrar `settings.APIMode` / request; default responses se vazio.

### C2. sso-watch

- Chave `seen` = name + mtime ou hash conteúdo.
- Opcional: mover arquivo para `sso-watch/imported/` após sucesso.

### C3. Bindings register

- Deprecar ou documentar `CreateAccount` como “bot only”.
- UI só chama `CreateAccounts` / `CreateAccountFromDevice`.
- Emit `register:progress` com step string para modal.

**Estimativa:** 2–3h

---

## Fase D — Produto agent + qualidade (P2)

**IDs:** H11–H14

### D1. Skills / MCP — decisão binária

**Opção X (ship):** UI mínima list/create skill + form MCP URL/env; ainda sem tool-call bridge.  
**Opção Y (cut):** remover de `GetBootstrap` inject até bridge existir; manter pacotes no disco.

Recomendação: **Y** até haver cliente MCP real, para não prometer “agent” no prompt.

### D2. Testes

| Teste | Foco |
|-------|------|
| store | IsExhausted 24h, Recover, PublicAccounts |
| proxy | mark + tried (mock transport 429→200) |
| recordUsage | CostUSD &gt; 0 com usage fixture |
| SSO parse | lines email:pass:token |

### D3. Frontend split

Módulos: `accounts.js`, `chat.js`, `stats.js`, `register.js` + `main.js` shell.

### D4. i18n leve

Ou PT-only documentado no README, ou chaves EN na UI.

**Estimativa:** 6–12h (split + tests dominam)

---

## Fora de escopo deste plano

- Reescrever bot em Playwright (DrissionPage ok se estável).
- MCP tool execution runtime.
- Encrypt AppData tokens (possível fase E security).
- macOS release pipeline.

---

## Ordem de merge sugerida

```
A1 → A2/A3 → B1/B4 → B2 → B3 → C* → D*
```

A1 e B1 são os que mais doem no uso diário (contas mortas + card $0 visual).

## Checklist mestre

### Fase A
- [x] AccountFromToken no auto-register
- [x] Settings auto_register_* + paths
- [x] Loop default off
- [x] Ctx bot/poll (melhoria)

### Fase B
- [x] OnUsage / OnAccountChange
- [x] Anthropic recordUsage
- [x] Desktop MarkAccountExhausted
- [x] Frontend paint on usage:update

### Fase C
- [x] API mode honrado ou UI limpa
- [x] sso-watch mtime/hash
- [x] register:progress + API clara

### Fase D
- [x] Skills/MCP: **option Y** — inject only real catalogs; no CREATE_SKILL marketing
- [x] Testes store + proxy usage/diagnose + failover 429→200
- [x] Frontend modules (`state`, `util`, `shell`, `chat`, `search-ui`, `stats`, `register-ui`, `menus`, `markdown`)
- [x] i18n: documented PT-BR UI in README (no full i18n framework)

## Status

| Fase | Status | Onde |
|------|--------|------|
| A | ✅ concluída | código + `plan/executed` |
| B | ✅ concluída | código + `plan/executed` |
| C | ✅ concluída | código + `plan/executed` |
| D | ✅ concluída (2026-07-09) — residual opcional cancelado/documentado | → mover p/ executed |

### Residual explicitamente **fora** / cancelado

- ~~H12 frontend split~~ ✅ feito
- ~~H11 Skills/MCP UI~~ **Y**: sem UI; backend store + catalog only; marketing prompt removido
- ~~H14 i18n framework~~ documentado PT-BR UI no README
- Packaging Python release / encrypt tokens — **fora de escopo** (Fase E / ops)

**Pronto para `plan/executed`.**
