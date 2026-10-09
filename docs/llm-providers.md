# LLM provider configuration

QueryMind works with one configured provider. It never requires all keys and never falls back to another provider automatically.

## UI configuration

Open **AI Settings**:

1. Select a provider.
2. Enter an API key (not required for local Ollama).
3. Select **Discover models**.
4. Choose a model returned for your account, or enter its exact identifier.
5. Adjust temperature and maximum output tokens.
6. Select **Test connection**.

UI keys are session-only. Use `.env` for persistent local configuration and restart after editing it.

## Google Gemini

```dotenv
GEMINI_API_KEY=
DEFAULT_AI_PROVIDER=gemini
DEFAULT_AI_MODEL=
```

The adapter lists models supporting content generation and uses the Gemini `v1beta` `generateContent` endpoint with JSON output mode. Model availability and free-tier eligibility depend on the Google account/project. Select a model returned by discovery instead of relying on a hardcoded name.

As verified on October 9, 2026, the configured project exposes `gemini-3.8-flash`, and Google's official pricing page lists standard Free Tier input and output for that model as free of charge. It is the preferred QueryMind candidate because it supports structured output and is positioned for complex software and agentic work. Discovery does not reveal whether an API project is currently Free Tier or linked to paid billing; confirm the project's tier in Google AI Studio before sending requests. Active quotas are also account-specific and must be checked in AI Studio.

Official references: [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [models](https://ai.google.dev/gemini-api/docs/models), and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

Official reference: [Gemini API](https://ai.google.dev/api).

## Groq

```dotenv
GROQ_API_KEY=
DEFAULT_AI_PROVIDER=groq
DEFAULT_AI_MODEL=
```

The adapter uses Groq's OpenAI-compatible base URL, `https://api.groq.com/openai/v1`, and discovers models through `/models`.

Official references: [Groq API](https://console.groq.com/docs/api-reference) and [OpenAI compatibility](https://console.groq.com/docs/openai).

## OpenRouter

```dotenv
OPENROUTER_API_KEY=
DEFAULT_AI_PROVIDER=openrouter
DEFAULT_AI_MODEL=
```

The adapter uses `https://openrouter.ai/api/v1`. Model discovery retains OpenRouter's pricing object. QueryMind labels a model free only when both returned prompt and completion prices are zero. Recheck pricing before use; model routes, availability, and pricing may change.

Official references: [model listing](https://openrouter.ai/docs/api/api-reference/models/get-models) and [chat completion](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request).

## Custom OpenAI-compatible provider

```dotenv
CUSTOM_LLM_NAME=My Provider
CUSTOM_LLM_BASE_URL=https://example.com
CUSTOM_LLM_API_KEY=
CUSTOM_LLM_MODEL=
ALLOW_LOCAL_CUSTOM_LLM=false
```

The base URL should be the provider origin or API prefix; QueryMind appends `/v1` when it is absent. The provider must support `/v1/chat/completions` and preferably `/v1/models`.

For SSRF protection, QueryMind resolves the hostname and rejects private, loopback, link-local, multicast, and reserved addresses. Set `ALLOW_LOCAL_CUSTOM_LLM=true` only when intentionally connecting to another localhost-compatible service. This opt-in does not allow arbitrary private-network hosts.

## Ollama (optional)

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
```

QueryMind only detects and uses models already available from the local Ollama service. It never installs Ollama or downloads a model. If Ollama is absent, provider testing/model discovery returns a normal connection error and the rest of the application remains usable.

The adapter uses Ollama's `/v1/chat/completions` and `/v1/models` compatibility endpoints and restricts this provider to loopback hostnames.

Official reference: [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

## Errors and quota behavior

- `401`/`403`: invalid key or account/model permission.
- `404`: model or endpoint unavailable.
- `429`: rate limit or quota exhausted; QueryMind makes at most two delayed transient retries, then asks the user to wait or explicitly select another model.
- timeout/network error or selected transient 5xx response: retried with bounded exponential backoff.

QueryMind does not claim that free quotas are unlimited. SQL validation, demo execution, charts, exports, history, and saved queries continue working without an AI request.

## Token minimization

- relevant-table schema selection;
- five-minute schema cache;
- compact prompt contract;
- bounded recent conversation;
- configurable output limit;
- no automatic insight request;
- at most 50 displayed rows in optional insight prompts;
- local Pandas statistics for larger result sets.
