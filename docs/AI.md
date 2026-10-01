# AI asistence (krok 11 / D12)

Default: **vypnuto** (`AI_ENABLED` unset/false). Bez klíčů se aplikace chová stejně jako po kroku 10.

## Zapnutí

```sh
# .env
AI_ENABLED=true
AI_PROVIDER=openai          # nebo anthropic
OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini
# ANTHROPIC_API_KEY=...
# AI_RATE_LIMIT_PER_MIN=10
```

## Scope

| Ano | Ne |
| --- | --- |
| Návrh / vylepšení **poznámky** u otázky | Autonomní nastavení ratingu na „splňuje“ |
| Volitelné shrnutí „co zbývá“ (`/api/ai/suggest-remaining`) | Sken celého repa místo skriptů 1–5 |
| Badge **Návrh AI** + `proposal_source=ai` | Zaměnění AI confidence za automat |

## API

- `GET /api/ai/status` / pole `ai` v `/api/config`
- `POST /api/ai/suggest-note` — tělo: `{ evaluation_id?, question: { text, evidence, note, … } }`
- Event `ai_suggest` v `EvaluationEvent`

Tajné tokeny v textu se před promptem redigují (`utils/ai_assist.redact_secrets`).
