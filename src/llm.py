"""
Groq LLM wrapper used by every step that needs an LLM.

- chat_json(): asks the model for JSON that must match a JSON schema (strict mode),
  so the output can always be parsed.
- Handles Groq free-tier rate limits: waits on short limits, and switches to the
  fallback model when the daily token limit of the main model is used up.
"""
import json
import time

import groq

from src import config


class DailyLimitReached(Exception):
    """All models have used up their daily quota. Re-run later; progress is cached."""


_client = None
_models = [config.GROQ_MODEL, config.GROQ_FALLBACK_MODEL]
_active = 0          # index into _models
usage = {"calls": 0, "tokens": 0}


def client():
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is missing from .env")
        _client = groq.Groq(api_key=config.GROQ_API_KEY, max_retries=0, timeout=120)
    return _client


def _retry_after(err):
    try:
        return float(err.response.headers.get("retry-after", 20))
    except Exception:
        return 20.0


def _default_for(prop):
    if "enum" in prop:
        return prop["enum"][-1]
    return {"string": "", "array": [], "boolean": False, "number": 0, "integer": 0, "object": {}}.get(prop.get("type"), None)


def _salvage(err, schema):
    """Groq rejects output that breaks the schema (e.g. one missing field) and returns it as
    'failed_generation'. If that text is valid JSON, fill the missing fields with safe defaults."""
    body = getattr(err, "body", None)
    gen = None
    if isinstance(body, dict):
        gen = body.get("failed_generation") or (body.get("error") or {}).get("failed_generation")
    if not gen:
        return None
    try:
        data = json.loads(gen)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    for key, prop in schema.get("properties", {}).items():
        if key not in data:
            data[key] = _default_for(prop)
    return data


def chat_json(system, user, schema, schema_name="result", max_tokens=8000):
    """Return the parsed JSON object produced by the model."""
    global _active
    attempts = 0
    while True:
        model = _models[_active]
        try:
            resp = client().chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                response_format={"type": "json_schema",
                                 "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
                temperature=0,
                reasoning_effort="low",
                include_reasoning=False,
                max_completion_tokens=max_tokens,
            )
            usage["calls"] += 1
            usage["tokens"] += resp.usage.total_tokens if resp.usage else 0
            return json.loads(resp.choices[0].message.content)

        except groq.RateLimitError as e:
            wait = _retry_after(e)
            if wait > 120:                       # daily quota for this model is used up
                if _active + 1 < len(_models):
                    _active += 1
                    print(f"    daily limit reached for {model}; switching to {_models[_active]}")
                    continue
                raise DailyLimitReached(f"Daily Groq limit reached (retry in ~{wait / 3600:.1f} h)") from e
            print(f"    rate limited, waiting {wait:.0f}s ...")
            time.sleep(wait + 1)

        except (groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError) as e:
            attempts += 1
            if attempts > 4:
                raise
            print(f"    {type(e).__name__}, retrying in {5 * attempts}s ...")
            time.sleep(5 * attempts)

        except (groq.BadRequestError, json.JSONDecodeError) as e:
            # usually the model failed to produce valid JSON for the schema
            salvaged = _salvage(e, schema) if isinstance(e, groq.BadRequestError) else None
            if salvaged is not None:
                usage["calls"] += 1
                return salvaged
            attempts += 1
            if attempts > 2:
                raise
            print(f"    bad response ({str(e)[:120]}), retrying ...")
