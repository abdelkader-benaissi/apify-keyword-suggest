# Keyword Suggest Research

Harvest **Google autocomplete keyword suggestions** over plain HTTP — no headless browser, no API key. Built for **SEO research** and **AI agents** that need long-tail keyword ideas fast.

Feed it one or more seed keywords and get back one dataset row per unique suggestion: the suggestion text, the seed it came from, its rank in the response, and the expanded query that produced it.

## What it does

- **Google Suggest API** — queries `suggestqueries.google.com`, the same endpoint behind the search-box autocomplete. Pure HTTP, ~5 requests/second.
- **Alphabet-soup expansion** — each seed is queried directly, plus `<seed> a` … `<seed> z` and `<seed> 0` … `<seed> 9` (37 queries per seed) to surface long-tail suggestions a single query would miss. Toggle with `expandAlphabet`.
- **Deduped** — a suggestion appearing under several expanded queries is kept once, with the rank and query of its first occurrence.
- **Language & country targeting** — `hl` / `gl` parameters (e.g. `fr` / `dz`) localize the suggestions.
- **Batch** — one seed per line; one bad seed never kills the batch.

## Input

| Field | Description |
|---|---|
| `keywords` | Seed keywords, one per line (required) |
| `language` | `hl` parameter, e.g. `en`, `fr`, `ar` (default `en`) |
| `country` | `gl` parameter, e.g. `us`, `fr`, `dz` (default `us`) |
| `expandAlphabet` | Query `<seed> a`…`<seed> z`, `<seed> 0`…`<seed> 9` (default on) |

Example input:

```json
{
  "keywords": "web scraping\napify",
  "language": "en",
  "country": "us",
  "expandAlphabet": true
}
```

## Output

One dataset row per unique suggestion:

| Field | Description |
|---|---|
| `seedKeyword` | The seed keyword the suggestion was collected for |
| `suggestion` | The autocomplete suggestion text |
| `rank` | Position in the Suggest API response (1-based) |
| `query` | The expanded query that produced it, e.g. `web scraping a` |

## Pricing

| Event | Price |
|---|---|
| Keyword researched | **$0.002** per seed keyword successfully processed |

You are only charged for seeds that are actually processed — failed seeds cost nothing. (Apify platform usage costs are paid by you as usual.)
