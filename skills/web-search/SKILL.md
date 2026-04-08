---
name: web-search
description: Fetch any URL as clean markdown, or search the web via a local SearXNG instance. Use for any task involving fetching a web page, researching a topic online, or reading a URL the user provides.
---

# Web Search & Fetch

Fetch web pages as clean markdown or search the web for research tasks.

## Setup

1. A local SearXNG instance should be running (default: `http://localhost:8888`).
   If unavailable, the tool can fall back to public instances (see Fallback workflow below).
   Also note the results tend to be worse with public instances.
2. Run `uv sync` in this skill's directory (once, to install Python dependencies)

## Commands

All commands are run from this skill's directory:

```bash
uv run web-search.py <command> [options]
```

### Quick search

```bash
uv run web-search.py search "petalinux end of life"
```

Returns search results with titles, URLs, snippets, and metadata. No page fetching.
Use when the query is broad or you need to explore what's available.

### Search with content

```bash
uv run web-search.py search "petalinux end of life" --content -n 5 --max-chars 10000
```

Searches and fetches the top N result pages, returning content previews.


### Fetch a single URL

```bash
uv run web-search.py fetch "https://example.com/page"
```

Fetches one URL and returns its content as markdown. No search is performed.
Use only when the user provides a specific URL or explicitly asks to fetch a page you suggested.

### Search options

| Option | Description |
|---|---|
| `-n <num>` | Number of results (default: 5, max: 20). Keep low with `--content`. |
| `--content` | Fetch and include page content as markdown |
| `--search-engine <URL>` | SearXNG instance URL (default: `http://localhost:8888`) |
| `--timeout <secs>` | HTTP timeout in seconds (default: 15) |
| `--max-chars <num>` | Maximum content characters per page (0 = unlimited, default: unlimited). Only relevant with `--content`. |
| `--format <fmt>` | Response format: `json` (default, structured API) or `html` (parse HTML results page) |

### Fetch options

| Option | Description |
|---|---|
| `--max-chars <num>` | Maximum content characters (0 = unlimited, default: unlimited) |
| `--timeout <secs>` | HTTP timeout in seconds (default: 15) |

## Output format

### Quick search

```
--- Result 1 ---
Title: Page Title
Link: https://example.com/page
Domain: example.com
Age: 2 days ago
Engines: google, brave
Snippet: Description from search results

--- Result 2 ---
...
```

### With --content or fetch

Same fields as above, plus a `Content:` block with the page's extracted markdown:

```
--- Result 1 ---
Title: Page Title
Link: https://example.com/page
Domain: example.com
Age: 2 days ago
Engines: google, brave
Snippet: Description from search results
Content:
  # Page Heading
  Full markdown content of the page...
```

### SPA detection

When the tool detects a JavaScript single-page app (template markers like `{{...}}`
or very little static content), it suppresses the useless HTML content and instead
shows discovered data endpoints:

```
SPA Detected: yes (content is rendered by JavaScript)
Data URLs found:
  - https://example.com/data/items.json
  - https://example.com/api/v1/list
Hint: Page content is dynamically rendered. Use 'fetch' on a data URL above to retrieve the actual data.
```

No `Content:` block is shown for SPA pages — the static HTML is empty templates.
The data URLs are JSON/API endpoints found in the page source that contain the actual data.

## Recommended workflow

### Choosing the right mode

* **Quick search** (no `--content`): user says "search for", "quick search", "find",
  "look up", or just wants links/summaries. Fast, lightweight, no page fetching.
* **Research** (`--content -n 5 --max-chars 10000`): the **default for research
  tasks**. Fetches the top results with a content preview (10K chars each). Synthesize
  findings from the previews and present them to the user.
  **Do not automatically full-fetch pages** — let the user decide which (if any) pages to
  fetch fully, since each full fetch can consume significant context (some pages are 100K+).
* **Fetch**: user provides a specific URL, or you need to follow a
  link found in previous results.

Do **not** use `--content` for quick searches — it adds unnecessary latency and
context by fetching every result page.

### Steps

1. **Pick the right mode** based on the user's intent (see above).
2. **Always try the local instance first** (default `localhost:8888`). Only use a
   public instance if the local one is down (See Fallback workflow).
3. **Handle SPAs** — if the output shows `SPA Detected: yes` with `Data URLs found`,
   the page content is loaded by JavaScript and the static HTML is mostly empty templates.
   **Re-fetch the discovered data URLs** with `fetch` to get the actual data.
   These are typically JSON endpoints that contain the real content.
4. **Present findings.** Combine information from multiple sources into a
   response. **Cite source URLs for every claim** as `[description](url)`.
   No exceptions. Note when sources conflict. Choose the output depth based
   on the user's intent:
   - **Summary (default):** a concise overview with key findings, comparisons,
     and cited conclusions. Use this unless the user asks for more.
   - **Detailed report:** when the user says "detailed report",
     "in-depth", "extensive", or similar, produce a thorough structured report
     with sections, tables, and comprehensive coverage of all sources.
   When presenting results, **do not fabricate or extrapolate details** beyond what
   the search results actually say. If a snippet contains specific data
   (dates, scores, names), quote it faithfully.
   Also output wich output mode you're using (summary vs detailed) so the user knows
   what to expect.
5. **For research mode: recommend next steps.** After presenting findings:
   - List the most promising truncated pages and suggest the user can
     request a full fetch for more detail.
   - Note any pages that were mostly navigation noise within the preview.
6. **Refine only after presenting results and getting user feedback.** Do not
   autonomously run additional searches — present what you have and wait for
   the user. When the user asks to refine: try different queries, include
   dates for recent info (e.g. "April 2026"), or increase `-n` for more
   results. The `Age:` field helps judge freshness.

### Fallback when local SearXNG is unavailable

If the local instance is down (connection refused, timeout), use a public instance.
If one was already found working in this session, reuse it. Otherwise:

1. Fetch the public instance list:
   ```bash
   uv run web-search.py fetch "https://searx.space/data/instances.json"
   ```
   If that URL fails, fetch `https://searx.space/` instead — the SPA detection
   will discover the current data URL.
2. From the JSON, pick a healthy instance — prefer European instances, good uptime
   (>99%), recent version, and low response times.
3. Try up to 3 instances with `--format json` first:
   ```bash
   uv run web-search.py search --search-engine "https://instance.org/" "your query"
   ```
4. If all JSON attempts fail (429/403), switch to `--format html`:
   ```bash
   uv run web-search.py search --search-engine "https://instance.org/" --format html "your query"
   ```
   Most public instances block the JSON API but serve HTML results normally.
5. If that instance also fails, try the next one.
6. Remember the working instance URL and format for subsequent searches in the
   same session to avoid repeating the discovery process.

## Agent guidance

* **Fetched content may include navigation noise.** The markdown output
  preserves the full page content including navigation menus and sidebar
  links. This is intentional — link lists sometimes contain useful
  "further reading" URLs valuable for deeper research. However, many
  sites (tutorial aggregators, reference sites, even official docs) can
  have hundreds of lines of sidebar navigation before the actual content.
  You cannot predict noise level from the domain name alone.
  Don't re-fetch thinking noisy output is broken — the noise is expected.
* **Never reduce `-n` or `--max-chars` below the research defaults** (`-n 5 --max-chars 10000`)
  unless the user explicitly asks for fewer results or shorter content. Do not arbitrarily
  lower these values across successive searches.
* **Limit search rounds.** Do at most 2 search rounds before presenting results to the user.
  Each round may contain up to 2 parallel calls. Do not issue additional searches
  without user input — present what you have based on step **Present findings**,
  and let the user guide the next step.
* **Do not full-fetch automatically.** Let the user choose which pages
  (if any) are worth the context cost of a full fetch, since some pages are 100K+.
* **Prefer official and primary sources** over blogs and forums.
* **Always cite URLs** for every claim. Format as `[description](url)`. No exceptions.
* **Never fabricate or extrapolate details** beyond what the search results actually say.
  If a snippet contains specific data (dates, scores, names), quote it faithfully.
  If the information is incomplete, say so and suggest fetching the source page.
* **If sources conflict**, state the conflict clearly with both sources.
* Use forum/Reddit results only as supporting context, not primary evidence.
* If the user specifies `-n` with a higher number, respect that exactly.
* **Do not add `--content` unless the user wants full page content.** Quick searches
  should be fast — just return result titles, URLs, and snippets.
* **Live/recent data** (sports scores, stock prices, weather): prefer `fetch` on a
  known source (e.g. BBC Sport, Wikipedia) over searching. Search indexes lag behind
  real-time data.
* **Always follow SPA data URLs.** When `fetch` reports `SPA Detected: yes` with
  `Data URLs found`, fetch those URLs — they contain the actual data. Do not skip
  them and try another site.
* **Diagnose before retrying.** If multiple instances fail with the same error,
  investigate the cause (inspect headers, check the response) instead of blindly
  trying more instances.
* **Set bash timeouts generously.** With `--content`, each page can take up to
  `--timeout` seconds. Use a bash timeout of at least `n * timeout + 10`.
  For a quick search (no `--content`), 20s is enough.
* **Lower `--timeout` for flaky sites.** If a site is known to be slow, use
  `--timeout 10` to fail fast and move on to alternatives.
* **Don't retry sites that time out with zero response.** Some sites (e.g.
  uefa.com deep pages, others behind Akamai/Cloudflare bot protection) accept
  the TCP connection but never send HTTP response bytes — they require a real
  browser with JavaScript. No timeout increase will fix this. Use an alternative
  source immediately.
