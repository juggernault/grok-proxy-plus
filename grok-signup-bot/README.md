# grok-signup-bot

Device-login browser automation + temporary email for Grok Desktop auto-register (see `docs/auto-register-plan-v1.md`).

## Phase A (this folder today)

Email providers only — no browser yet.

```bash
cd grok-signup-bot
python3 email_mailtm.py          # create Mail.tm inbox (smoke)
python3 -c "
from email_provider import build_providers, create_inbox_with_fallback
ps = build_providers(['mailtm'])
inbox = create_inbox_with_fallback(ps)
print(inbox['address'], inbox['provider'])
"
```

### Providers

| Name | Env / args | Notes |
|------|------------|--------|
| `mailtm` | none | Default, public API |
| `duckmail` | `DUCKMAIL_URL`, `DUCKMAIL_KEY` | Self-hosted; paths may need tweak for your fork |

Fallback: try providers in order only for **create_inbox**. After email is submitted to xAI, OTP is polled on the **same** provider (no mid-switch).

## Phase B (next)

- `grok_signup.py` — Playwright device → signup → Allow
- `turnstile_patch/` — Chrome extension
- Go `internal/register/bot.go` — subprocess + progress

## Protocol for Go (stdout)

```
__STEP__ email mailtm
__STEP__ otp
__RESULT__ {"status":"success"}
```
