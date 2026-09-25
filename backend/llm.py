"""Mistral chat in JSON mode. Used for writing (summary, SAR narrative, pattern description), never for decisions."""
import json
import os
import time

import httpx

URL = "https://api.mistral.ai/v1/chat/completions"


def available() -> bool:
    return bool(os.environ.get("MISTRAL_API_KEY"))


def write_json(system: str, facts: dict) -> tuple[dict | None, int]:
    """Returns (parsed JSON, tokens used). (None, 0) when no key is set or the call fails, so runs stay reproducible."""
    if not available():
        return None, 0
    try:
        for attempt in range(5):  # free tiers allow ~1 request/s; back off on 429 instead of losing the prose
            r = httpx.post(
                URL,
                headers={"Authorization": f"Bearer {os.environ['MISTRAL_API_KEY']}"},
                json={
                    "model": os.environ.get("MISTRAL_MODEL", "ministral-14b-latest"),
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(facts, default=str)},
                    ],
                },
            timeout=60,
            )
            if r.status_code != 429:
                break
            time.sleep(2 ** attempt)
        r.raise_for_status()
        body = r.json()
        return json.loads(body["choices"][0]["message"]["content"]), int(body.get("usage", {}).get("total_tokens", 0))
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
        print(f"  mistral: {type(e).__name__}: {e} (falling back to template text)")
        return None, 0
