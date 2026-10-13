"""Keyword Suggest Research actor: Google autocomplete suggestions over plain HTTP.

For each seed keyword the actor queries Google's public Suggest API
(``suggestqueries.google.com``) — the same endpoint that powers the search-box
autocomplete — optionally expanding each seed into ``"<seed> a"`` …
``"<seed> z"`` and ``"<seed> 0"`` … ``"<seed> 9"`` (the classic alphabet-soup
technique) to harvest many more long-tail suggestions. No browser, no API key;
polite rate limiting (~5 requests/second).

Pay-per-event (``keyword-researched``) is charged once per seed keyword that
was successfully processed — only after its rows were pushed to the dataset,
never on failure.
"""

import asyncio
import time

import httpx
from apify import Actor

EVENT_KEYWORD = 'keyword-researched'

SUGGEST_URL = 'https://suggestqueries.google.com/complete/search'

REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    ),
}

# Polite rate limit: at most ~5 Suggest API requests per second.
MIN_REQUEST_INTERVAL = 0.2


async def fetch_suggestions(client: httpx.AsyncClient, query: str,
                            language: str, country: str) -> list[str]:
    """Query the Suggest API. Returns suggestion strings; empty list on no data.

    Response shape: ["query", ["suggestion1", "suggestion2", ...], ...].
    Never raises for empty/malformed payloads — those yield [].
    """
    params = {'client': 'firefox', 'q': query,
              'hl': language, 'gl': country}
    resp = await client.get(SUGGEST_URL, params=params, timeout=15.0)
    resp.raise_for_status()
    try:
        data = resp.json()
    except ValueError:
        return []
    if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
        return [str(s) for s in data[1] if s is not None]
    return []


def expand_queries(seed: str) -> list[str]:
    """Seed plus alphabet-soup expansions: 1 + 26 + 10 = 37 queries."""
    queries = [seed]
    for ch in 'abcdefghijklmnopqrstuvwxyz':
        queries.append(f'{seed} {ch}')
    for digit in '0123456789':
        queries.append(f'{seed} {digit}')
    return queries


async def charge_event(event_name: str) -> None:
    """Bill one pay-per-event charge. Never let billing break the run."""
    try:
        await Actor.charge(event_name=event_name)
    except Exception as exc:
        Actor.log.warning(f'Pay-per-event charge {event_name!r} failed: {exc}')


def build_client() -> httpx.AsyncClient:
    """Build the HTTP client.

    Falls back to ignoring environment proxies if the environment's proxy
    config is malformed — a broken proxy config must not kill runs.
    """
    try:
        return httpx.AsyncClient(headers=REQUEST_HEADERS, timeout=15.0)
    except Exception as exc:
        Actor.log.warning(f'Unusable proxy environment ({exc}); '
                          'continuing without env proxies.')
        return httpx.AsyncClient(headers=REQUEST_HEADERS, timeout=15.0,
                                 trust_env=False)


def parse_keywords(raw) -> list[str]:
    if isinstance(raw, str):
        return [k.strip() for k in raw.splitlines() if k.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(k).strip() for k in raw if str(k).strip()]
    return []


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}
        seeds = parse_keywords(inp.get('keywords'))
        language = (str(inp.get('language') or 'en')).strip() or 'en'
        country = (str(inp.get('country') or 'us')).strip() or 'us'
        expand = bool(inp.get('expandAlphabet', True))

        if not seeds:
            await Actor.set_value('OUTPUT', {
                'seeds': 0,
                'seedsProcessed': 0,
                'suggestions': 0,
                'error': 'no keywords provided',
            })
            return

        total_suggestions = 0
        seeds_processed = 0
        last_request = 0.0

        async with build_client() as client:
            for seed in seeds:
                queries = expand_queries(seed) if expand else [seed]
                seen: set[str] = set()
                pushed_ok = 0
                for query in queries:
                    # Polite rate limiting.
                    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - last_request)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    last_request = time.monotonic()
                    try:
                        suggestions = await fetch_suggestions(
                            client, query, language, country)
                    except Exception as exc:
                        Actor.log.warning(
                            f'Suggest query {query!r} failed: '
                            f'{type(exc).__name__}: {exc}')
                        continue
                    if not suggestions:
                        # Empty response is normal (e.g. "<seed> q" has no
                        # completions) — log and continue, never crash.
                        Actor.log.info(f'No suggestions for {query!r}')
                        continue
                    for rank, suggestion in enumerate(suggestions, start=1):
                        text = suggestion.strip()
                        key = text.lower()
                        if not key or key in seen:
                            continue
                        seen.add(key)
                        item = {
                            'seedKeyword': seed,
                            'suggestion': text,
                            'rank': rank,
                            'query': query,
                        }
                        try:
                            # Push first; charge only after successful delivery.
                            await Actor.push_data(item)
                        except Exception as exc:
                            Actor.log.warning(
                                f'push_data failed for {text!r}: {exc}')
                            continue
                        pushed_ok += 1
                        total_suggestions += 1

                if pushed_ok:
                    seeds_processed += 1
                    # Charge once per processed seed, after its rows landed.
                    await charge_event(EVENT_KEYWORD)
                else:
                    Actor.log.warning(
                        f'Seed {seed!r}: nothing was pushed, not charged')

        await Actor.set_value('OUTPUT', {
            'seeds': len(seeds),
            'seedsProcessed': seeds_processed,
            'suggestions': total_suggestions,
        })
