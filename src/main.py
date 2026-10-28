from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import re
from urllib.parse import quote, urljoin, urlparse, urlunparse

from apify import Actor
from bs4 import BeautifulSoup
import httpx

PROTO = "https" + "://"
HTTP_PROTO = "http" + "://"
MAKE_BASE = f"{PROTO}www.make.com"
DIR_PATH = "/en/partners-directory"

SEED_SLUGS = [
    "business-automated",
    "the-automation-partner",
    "blinno-gmbh",
    "seamless-automation",
    "uptime-bots-adam-debski",
    "callbox",
    "meticulosity",
    "flow-digital",
    "byte-intelligence",
    "imara-software-solutions",
    "work-management-tools",
    "curated-services",
    "timlittletech",
    "integratingme",
    "axanexa-llc",
    "workiflow",
    "fifty-tech-solutions",
    "axe-automation",
    "neworkflow",
    "work-ninjas",
    "flowmondo",
    "9x",
    "flowbird-ltd",
    "lotic-digital-llc",
    "ioa-digital",
    "makeitfuture-srl",
]

KNOWN_APPS = [
    "OpenAI - ChatGPT / Whisper / DALL-E",
    "Anthropic Claude",
    "Airtable",
    "HubSpot CRM",
    "Salesforce",
    "Stripe",
    "Shopify",
    "Monday.com",
    "ClickUp",
    "Notion",
    "Asana",
    "Pipedrive",
    "QuickBooks",
    "Xero",
    "DocuSign",
    "ActiveCampaign",
    "Softr.io",
    "Bubble",
    "Glide",
    "Dropbox",
    "Aircall",
    "Brevo",
    "Customer.io",
    "AWS",
    "Microsoft Dynamics 365",
    "Microsoft 365 - MS Office",
    "Meta Social Media",
    "Google Workspace",
    "Slack",
]

KNOWN_SERVICES = [
    "Enterprise automation",
    "Basic workflow automation",
    "Consulting",
    "Training",
    "Migration from third party to Make",
    "Migration from Integromat to Make",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,12}")
BAD_EMAIL_EXT = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|css|js|woff|ttf|ico|pdf)$", re.I)
BAD_EMAIL_WORDS = re.compile(
    r"(sentry|example|domain|email\.com|yoursite|wixpress|cloudflare|placeholder|u00|make\.com|celonis\.com|integromat\.com)",
    re.I,
)
DOMAIN_TOKEN_RE = re.compile(
    r"\b(?:www\.)?[a-zA-Z0-9-]{2,63}\.(?:com|io|co|ai|dev|net|org|agency|tools|ch|de|uk|co\.uk|co\.il|ca|es|fr|nl|pl|eu|tech|digital|app|studio)(?:/[a-zA-Z0-9/_-]*)?\b",
    re.I,
)


def clean_email(raw: str) -> str:
    e = re.sub(r"^mailto:", "", raw or "", flags=re.I).split("?")[0].strip().lower()
    if not re.match(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,12}$", e):
        return ""
    if BAD_EMAIL_EXT.search(e) or BAD_EMAIL_WORDS.search(e):
        return ""
    return e


def normalize_url(raw_url: str) -> str:
    u = str(raw_url or "").strip().rstrip(".,;)")
    if not u:
        return ""
    if not u.startswith((PROTO, HTTP_PROTO)):
        u = f"{PROTO}{u}"
    try:
        p = urlparse(u)
        if not p.netloc or "." not in p.netloc:
            return ""
        return urlunparse((p.scheme, p.netloc.lower(), p.path, "", "", ""))
    except Exception:
        return ""


async def fetch_html(client: httpx.AsyncClient, url: str, timeout: float = 10.0) -> str:
    try:
        resp = await client.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return ""


async def resolve_clearbit_domain(client: httpx.AsyncClient, company_name: str) -> str:
    cleaned = re.sub(r"\|.*$", "", company_name or "").strip()
    if not cleaned or len(cleaned) < 2:
        return ""
    try:
        cb_url = f"{PROTO}autocomplete.clearbit.com/v1/companies/suggest?query={quote(cleaned)}"
        resp = await client.get(cb_url, timeout=4.0)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                domain = data[0].get("domain")
                if domain and "make.com" not in domain:
                    return f"{PROTO}{domain}"
    except Exception:
        pass
    return ""


def scan_soup_for_contacts(
    soup: BeautifulSoup,
    base_url: str,
    emails: set[str],
    phones: set[str],
    socials: dict[str, str],
) -> None:
    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if not href:
            continue
        low = href.lower()
        if low.startswith("mailto:"):
            ce = clean_email(href)
            if ce:
                emails.add(ce)
        elif low.startswith("tel:"):
            ph = re.sub(r"^tel:", "", href, flags=re.I).strip()
            if 7 <= len(ph) <= 22:
                phones.add(str(ph))
        elif re.search(r"linkedin\.com/(company|in)/", href, re.I) and not socials["linkedinUrl"]:
            if "make-com" not in low and "integromat" not in low:
                socials["linkedinUrl"] = str(href.split("?")[0])
        elif (
            re.search(r"(twitter\.com|x\.com)/[a-z0-9_]+", href, re.I)
            and not re.search(r"intent|share|make_hq", href, re.I)
            and not socials["twitterUrl"]
        ):
            socials["twitterUrl"] = str(href.split("?")[0])
        elif re.search(r"youtube\.com/(c/|channel/|@)[a-z0-9_-]+", href, re.I) and not socials["youtubeUrl"]:
            if "make" not in low:
                socials["youtubeUrl"] = str(href.split("?")[0])
        elif not socials["contactPageUrl"] and re.search(
            r"/(contact|about|get-in-touch|talk-to-us|book|schedule)", href, re.I
        ):
            try:
                resolved = urljoin(base_url, href)
                if "make.com" not in resolved.lower():
                    socials["contactPageUrl"] = str(resolved)
            except Exception:
                pass

    for raw in EMAIL_RE.findall(soup.get_text(" ", strip=True)):
        ce = clean_email(raw)
        if ce:
            emails.add(ce)


async def enrich_external_website(
    client: httpx.AsyncClient,
    website_url: str,
    initial_emails: set[str] | None = None,
    initial_linkedin: str = "",
    initial_youtube: str = "",
) -> dict:
    emails: set[str] = set(initial_emails or set())
    phones: set[str] = set()
    socials: dict[str, str] = {
        "linkedinUrl": str(initial_linkedin or ""),
        "twitterUrl": "",
        "youtubeUrl": str(initial_youtube or ""),
        "contactPageUrl": "",
    }

    if website_url and "linkedin.com" not in website_url.lower():
        html = await fetch_html(client, website_url, timeout=8.0)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            scan_soup_for_contacts(soup, website_url, emails, phones, socials)

            if not emails and socials["contactPageUrl"]:
                contact_html = await fetch_html(client, socials["contactPageUrl"], timeout=6.0)
                if contact_html:
                    scan_soup_for_contacts(
                        BeautifulSoup(contact_html, "html.parser"),
                        socials["contactPageUrl"],
                        emails,
                        phones,
                        socials,
                    )

    sorted_emails = sorted(emails)[:10]
    return {
        "primaryEmail": sorted_emails[0] if sorted_emails else "",
        "emails": sorted_emails,
        "phones": sorted(phones)[:5],
        "linkedinUrl": str(socials["linkedinUrl"] or ""),
        "twitterUrl": str(socials["twitterUrl"] or ""),
        "youtubeUrl": str(socials["youtubeUrl"] or ""),
        "contactPageUrl": str(socials["contactPageUrl"] or ""),
    }


def sanitize_record(record: dict) -> dict:
    clean: dict = {}
    for k, v in record.items():
        if v is None:
            clean[k] = ""
        elif isinstance(v, list):
            clean[k] = [str(x) for x in v if x is not None and str(x).strip() != ""]
        elif isinstance(v, int):
            clean[k] = int(v)
        else:
            clean[k] = str(v)
    return clean


def extract_labeled_value(full_text: str, label: str, stop_labels: list[str]) -> str:
    stop_pat = "|".join(re.escape(s) for s in stop_labels)
    pattern = rf"{re.escape(label)}\s+(.+?)(?=\s+(?:{stop_pat})\b|$)"
    m = re.search(pattern, full_text, flags=re.I)
    return m.group(1).strip() if m else ""


async def process_make_partner(
    slug: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    partner_tier_filter: str,
    search_query: str,
    enrich_contacts: bool,
) -> dict | None:
    profile_url = f"{MAKE_BASE}{DIR_PATH}/{slug}"
    async with semaphore:
        html = await fetch_html(client, profile_url, timeout=12.0)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        title_tag = soup.find("title")
        raw_title = title_tag.get_text(strip=True) if title_tag else ""
        partner_name = (
            h1.get_text(strip=True)
            if h1 and h1.get_text(strip=True)
            else re.split(r"\||-", raw_title)[0].strip() or slug
        )

        # Strip global header/footer noise so we focus on the partner profile content
        main_el = soup.find("main") or soup
        full_text = re.sub(r"\s+", " ", main_el.get_text(" ", strip=True))

        # 1. Partner Tier
        partner_tier = "Certified partner"
        for badge in ["Platinum partner", "Gold partner", "Silver partner", "Certified partner"]:
            if re.search(re.escape(badge), full_text, re.I):
                partner_tier = badge
                break

        if partner_tier_filter != "all" and partner_tier_filter.lower() not in partner_tier.lower():
            return None

        # 2. Extract Website, LinkedIn, YouTube, Emails from profile page
        profile_emails: set[str] = set()
        for raw_e in EMAIL_RE.findall(full_text):
            ce = clean_email(raw_e)
            if ce:
                profile_emails.add(ce)

        external_website = ""
        profile_linkedin = ""
        profile_youtube = ""

        for a in main_el.find_all("a", href=True):
            href = (a["href"] or "").strip()
            low = href.lower()
            if not href.startswith((PROTO, HTTP_PROTO)):
                continue
            if "linkedin.com/" in low and "make" not in low:
                if not profile_linkedin:
                    profile_linkedin = href.split("?")[0]
                continue
            if "youtube.com/" in low and "make" not in low:
                if not profile_youtube:
                    profile_youtube = href.split("?")[0]
                continue
            if not re.search(
                r"make\.com|celonis\.com|integromat\.com|linkedin\.com|twitter\.com|x\.com|facebook\.com|instagram\.com|youtube\.com|calendly\.com",
                low,
            ):
                external_website = normalize_url(href)
                if external_website:
                    break

        # Fallback: Make.com profile pages often render the agency domain as plain text after Language/Website
        if not external_website:
            for m in DOMAIN_TOKEN_RE.finditer(full_text):
                candidate = m.group(0).strip()
                low_c = candidate.lower()
                if any(
                    bad in low_c
                    for bad in (
                        "make.com",
                        "celonis.com",
                        "softr.io",
                        "monday.com",
                        "customer.io",
                        "linkedin.com",
                        "youtube.com",
                    )
                ):
                    continue
                external_website = normalize_url(candidate)
                if external_website:
                    break

        if not external_website and enrich_contacts:
            external_website = await resolve_clearbit_domain(client, partner_name)

        # 3. Extract App Specializations & Services
        app_specs: list[str] = []
        for app_name in KNOWN_APPS:
            if re.search(r"\b" + re.escape(app_name) + r"\b", full_text, re.I):
                app_specs.append(app_name)

        services: list[str] = []
        for srv in KNOWN_SERVICES:
            if re.search(re.escape(srv), full_text, re.I):
                services.append(srv)

        # 4. Extract Locations & Languages
        locations: list[str] = []
        loc_block = extract_labeled_value(
            full_text,
            "Countries with office locations",
            ["Realize your business", "Bring automation", "Talk to sales", "Type of services"],
        ) or extract_labeled_value(
            full_text,
            "Location",
            ["Certified", "Gold partner", "Platinum partner", "Silver partner", "Language", "Website"],
        )
        if loc_block:
            for part in loc_block.split(","):
                p_clean = part.strip(" .•*")
                if p_clean and len(p_clean) < 40 and p_clean not in locations:
                    locations.append(p_clean)

        if not locations:
            for country in [
                "United States", "United Kingdom", "Germany", "Canada", "Australia",
                "France", "Switzerland", "Spain", "Poland", "Israel", "Denmark",
                "Netherlands", "India", "Argentina", "Mexico", "Cyprus", "Ireland",
            ]:
                if re.search(r"\b" + re.escape(country) + r"\b", full_text, re.I):
                    locations.append(country)

        languages: list[str] = []
        for lang in [
            "English", "German", "Spanish", "French", "Polish",
            "Portuguese", "Hebrew", "Dutch", "Italian", "Arabic",
        ]:
            if re.search(r"\b" + re.escape(lang) + r"\b", full_text, re.I):
                languages.append(lang)

        # 5. Summary / About text
        about_text = extract_labeled_value(
            full_text,
            "About",
            ["Type of services", "Countries with office locations", "Bring automation", "Realize your business"],
        )
        meta_desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
            "meta", attrs={"property": "og:description"}
        )
        meta_desc = (
            meta_desc_tag["content"].strip()
            if meta_desc_tag and meta_desc_tag.get("content")
            else ""
        )
        summary = (about_text or meta_desc)[:500].strip()
        headquarters = locations[0] if locations else "Global"

        if search_query:
            hay = (
                f"{partner_name} {partner_tier} {' '.join(app_specs)} "
                f"{' '.join(services)} {' '.join(locations)} {summary} {external_website}"
            ).lower()
            if search_query.lower() not in hay:
                return None

        if enrich_contacts:
            contact_data = await enrich_external_website(
                client,
                external_website,
                profile_emails,
                profile_linkedin,
                profile_youtube,
            )
        else:
            sorted_pe = sorted(profile_emails)[:10]
            contact_data = {
                "primaryEmail": sorted_pe[0] if sorted_pe else "",
                "emails": sorted_pe,
                "phones": [],
                "linkedinUrl": profile_linkedin,
                "twitterUrl": "",
                "youtubeUrl": profile_youtube,
                "contactPageUrl": "",
            }

        record = {
            "partnerName": str(partner_name or slug),
            "slug": str(slug),
            "partnerTier": str(partner_tier),
            "headquarters": str(headquarters),
            "website": str(external_website or ""),
            "primaryEmail": str(contact_data["primaryEmail"] or ""),
            "emails": list(contact_data["emails"]),
            "phones": list(contact_data["phones"]),
            "linkedinUrl": str(contact_data["linkedinUrl"] or ""),
            "twitterUrl": str(contact_data["twitterUrl"] or ""),
            "youtubeUrl": str(contact_data["youtubeUrl"] or ""),
            "contactPageUrl": str(contact_data["contactPageUrl"] or ""),
            "appSpecializations": app_specs,
            "services": services,
            "locations": locations,
            "languages": languages,
            "summary": str(summary),
            "profileUrl": str(profile_url),
            "scrapedAt": datetime.now(timezone.utc).isoformat(),
        }
        return sanitize_record(record)


async def discover_make_partner_slugs(client: httpx.AsyncClient, max_items: int) -> list[str]:
    discovered: list[str] = []
    seen: set[str] = set()

    def add_slug(raw_s: str) -> None:
        s = raw_s.strip().strip("/").lower()
        if s and s not in ("en", "partners-directory", "partners") and re.match(r"^[a-z0-9-]+$", s):
            if s not in seen:
                seen.add(s)
                discovered.append(s)

    # 1. Check Make.com sitemap & directory landing page
    for url in (
        f"{MAKE_BASE}/sitemap.xml",
        f"{MAKE_BASE}/en/sitemap.xml",
        f"{MAKE_BASE}{DIR_PATH}",
    ):
        text = await fetch_html(client, url, timeout=10.0)
        if not text:
            continue
        for m in re.finditer(r"/en/partners-directory/([a-zA-Z0-9-]+)", text):
            add_slug(m.group(1))
        if len(discovered) >= max_items * 3:
            break

    # 2. Always include verified curated Make.com Certified/Silver/Gold/Platinum partner slugs
    for s in SEED_SLUGS:
        add_slug(s)

    return discovered


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        search_query = str(actor_input.get("searchQuery") or "").strip()
        partner_tier_filter = str(actor_input.get("partnerTierFilter") or "all").strip()
        max_items = int(actor_input.get("maxItems") or 25)
        enrich_contacts = bool(actor_input.get("enrichWebsiteContacts", True))

        Actor.log.info(
            f"Starting Make.com Certified Partner & AI Agency Enricher "
            f"(maxItems={max_items}, tier='{partner_tier_filter}', enrich={enrich_contacts})"
        )

        async with httpx.AsyncClient() as client:
            discovered_slugs = await discover_make_partner_slugs(client, max_items)
            Actor.log.info(f"Total unique Make.com Partner profiles queued: {len(discovered_slugs)}")

            semaphore = asyncio.Semaphore(8)
            saved_count = 0
            batch_size = 10

            for i in range(0, len(discovered_slugs), batch_size):
                if saved_count >= max_items:
                    break
                chunk = discovered_slugs[i : i + batch_size]
                tasks = [
                    process_make_partner(
                        slug,
                        client,
                        semaphore,
                        partner_tier_filter,
                        search_query,
                        enrich_contacts,
                    )
                    for slug in chunk
                ]
                results = await asyncio.gather(*tasks)
                for record in results:
                    if not record or saved_count >= max_items:
                        continue
                    try:
                        await Actor.push_data(record)
                        saved_count += 1
                        try:
                            await Actor.charge(event_name="partner-enriched", count=1)
                        except Exception:
                            pass
                        Actor.log.info(
                            f"[{saved_count}/{max_items}] Enriched Make.com Partner: "
                            f"{record['partnerName']} ({record['partnerTier']}) | "
                            f"Site: {record['website'] or 'no-site'} | Emails: {len(record['emails'])}"
                        )
                    except Exception as exc:
                        Actor.log.warning(f"Skipped invalid record: {exc}")

        Actor.log.info(f"Finished run! Total Make.com Partner B2B leads pushed: {saved_count}")
