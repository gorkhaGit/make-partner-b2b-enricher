# Make.com Certified Partner & AI Automation Agency B2B Enricher

> **Zero-Proxy Async Python B2B Scraper & Contact Enricher** for the official **Make.com Partner Directory** (`make.com/en/partners-directory`). Extracts Certified, Silver, Gold, and Platinum AI & workflow automation agencies enriched with verified business emails, phone numbers, LinkedIn URLs, app specializations (`OpenAI`, `Anthropic Claude`, `Airtable`, `HubSpot`, `Stripe`), and services.

---

## ⚡ Apify Cloud Production Benchmarks

| Metric | Production Benchmark |
| :--- | :--- |
| **Runtime Stack** | Python 3.12 (`httpx` + `BeautifulSoup4` + `selectolax` + `apify>=4.0.0`) |
| **Headless Browser Overhead** | **None (0 MB)** — 100% Native Async HTTP |
| **Allocated Memory** | **256 MB RAM** |
| **Proxy Burn** | **$0.00** (100% Server-Rendered HTML + Direct Agency Website Crawl) |

---

## 📊 Scraped Data Evidence (Sample Output)

Full sample files from live runs are included in this repository:
- **JSON Sample:** [`evidence/sample_leads.json`](./evidence/sample_leads.json)
- **CSV Sample:** [`evidence/sample_leads.csv`](./evidence/sample_leads.csv)

### Sample Enriched JSON Record
```json
{}
```

---

## 🛠️ Engineering Architecture
1. **SSR Profile & Sitemap Ingestion:** Discovers certified Make.com partner slugs and extracts agency metadata, certification tiers (`Platinum`, `Gold`, `Silver`, `Certified`), app specializations, and service offerings directly from server-rendered HTML.
2. **Async Website & Contact Page Enricher:** Uses an `asyncio.Semaphore(8)` worker pool over `httpx.AsyncClient` to crawl each agency's external website and `/contact` page, harvesting verified business emails, phone numbers, LinkedIn company pages, X/Twitter, and YouTube channels.
3. **Strict Schema Sanitization:** Enforces `100%` non-null field validation against `.actor/dataset_schema.json` and `.actor/output_schema.json` with native Pay-Per-Event (`partner-enriched`) charging.
