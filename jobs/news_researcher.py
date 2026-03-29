"""
news_researcher.py — Fetches news via NewsAPI and synthesizes with Groq LLM.

Two public functions:
  fetch_raw_results(queries)  → flat list of deduped article dicts
  research_sector(sector)     → structured dict ready for the email builder
"""

import json
import logging
import requests

from groq import Groq

import config

logger = logging.getLogger(__name__)

_groq_client = Groq(api_key=config.GROQ_API_KEY)

# ── Sector definitions ────────────────────────────────────────────────────────

SECTORS = [
    {
        "name": "AI & Machine Learning",
        "icon": "🤖",
        "queries": [
            "artificial intelligence news today",
            "large language model release today",
            "AI research paper breakthrough this week",
            "OpenAI Anthropic Google DeepMind news today",
            "machine learning tools frameworks released today",
        ],
    },
    {
        "name": "Dev Tools & Open Source",
        "icon": "💻",
        "queries": [
            "developer tools release github today",
            "open source project launch this week",
            "programming framework update today",
            "VS Code JetBrains developer news today",
            "software engineering best practices news today",
        ],
    },
    {
        "name": "Startups & Venture Capital",
        "icon": "🚀",
        "queries": [
            "tech startup funding round today",
            "India startup funding news today",
            "Y Combinator startup news this week",
            "venture capital investment tech today",
            "startup acquisition merger tech today",
        ],
    },
    {
        "name": "Big Tech",
        "icon": "🏢",
        "queries": [
            "Google news today technology",
            "Microsoft product announcement today",
            "Apple Meta Amazon tech news today",
            "big tech regulation policy news today",
            "FAANG company earnings strategy news today",
        ],
    },
    {
        "name": "Cybersecurity",
        "icon": "🔒",
        "queries": [
            "cybersecurity breach attack today",
            "data breach news today",
            "vulnerability CVE security patch today",
            "ransomware malware news today",
            "cybersecurity regulation compliance news today",
        ],
    },
    {
        "name": "India Tech",
        "icon": "🇮🇳",
        "queries": [
            "India technology startup news today",
            "ISRO space technology India news today",
            "Bengaluru Hyderabad tech hub news today",
            "Indian government digital policy AI news today",
            "India tech unicorn funding news today",
        ],
    },
]

# ── NewsAPI fetcher ───────────────────────────────────────────────────────────

def fetch_raw_results(queries: list) -> list:
    """Fetch news articles from NewsAPI for all queries, deduplicated by URL."""
    seen_links = set()
    all_results = []

    for query in queries:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": query,
                    "sortBy": "publishedAt",
                    "pageSize": 5,
                    "apiKey": config.NEWSAPI_KEY,
                    "language": "en",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            for article in data.get("articles", []):
                link = article.get("url", "")
                if not link or link in seen_links:
                    continue
                seen_links.add(link)
                all_results.append(
                    {
                        "title": article.get("title", ""),
                        "snippet": article.get("description", "") or "",
                        "source": (article.get("source") or {}).get("name", ""),
                        "link": link,
                        "date": article.get("publishedAt", ""),
                    }
                )
        except Exception as e:
            logger.warning(f"NewsAPI query failed [{query!r}]: {e}")

    return all_results[:25]  # cap at 25 articles per sector


# ── Groq synthesis ────────────────────────────────────────────────────────────

# Uses double-braces {{}} so the JSON structure survives .format(sector_name=...)
_SYSTEM_PROMPT_TEMPLATE = """You are a technology research analyst writing for a computer science student in India.
Analyze the following news items and produce a structured JSON response.

STRICT JSON FORMAT — respond with ONLY valid JSON, no markdown:
{{
  "stories": [
    {{
      "headline": "Clear, specific headline (not clickbait)",
      "summary": "2-3 paragraph detailed summary. Be specific — mention company names, numbers, dates, technical details. Do not be vague.",
      "key_points": ["point 1", "point 2", "point 3", "point 4"],
      "why_it_matters": "1 paragraph explaining relevance to a CS student in India — career impact, skill relevance, industry direction.",
      "citations": [
        {{"title": "exact article title", "source": "publication name", "url": "exact url"}}
      ]
    }}
  ],
  "tldr": "2-sentence overall summary of today's {sector_name} landscape."
}}

Rules:
- 3 to 5 stories. Pick the most significant, not just the most recent.
- Each citation must come from the actual source URLs provided.
- Never fabricate URLs, titles, or facts.
- If multiple sources cover the same story, combine them into one story with multiple citations.
- key_points must be specific facts, not generic statements.
"""


def research_sector(sector: dict) -> dict:
    """Fetch raw news for a sector and synthesize into structured stories via Groq."""
    raw_results = fetch_raw_results(sector["queries"])

    if not raw_results:
        logger.warning(f"No raw results for sector: {sector['name']}")
        return {
            "sector_name": sector["name"],
            "icon": sector["icon"],
            "stories": [],
            "tldr": "No news data available for this sector today.",
        }

    # Build the prompt user-content block
    raw_text = "\n".join(
        f"SOURCE: {r['source']}\nTITLE: {r['title']}\nSNIPPET: {r['snippet']}\nURL: {r['link']}\n---"
        for r in raw_results
    )

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(sector_name=sector["name"])

    # Keep a reference outside the try so the except block can access it
    llm_response = None
    try:
        llm_response = _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Here are the news items for {sector['name']}:\n\n{raw_text}",
                },
            ],
        )

        raw_json = llm_response.choices[0].message.content.strip()

        # Strip accidental markdown code fences
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
            raw_json = raw_json.strip()

        parsed = json.loads(raw_json)

        return {
            "sector_name": sector["name"],
            "icon": sector["icon"],
            "stories": parsed.get("stories", []),
            "tldr": parsed.get("tldr", ""),
        }

    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for {sector['name']}: {e}")
        # Fallback: wrap the raw LLM text in a single story so something is emailed
        raw_content = (
            llm_response.choices[0].message.content
            if llm_response is not None
            else "Could not parse LLM output."
        )
        return {
            "sector_name": sector["name"],
            "icon": sector["icon"],
            "stories": [
                {
                    "headline": f"Today in {sector['name']}",
                    "summary": raw_content,
                    "key_points": [],
                    "why_it_matters": "",
                    "citations": [],
                }
            ],
            "tldr": f"Summary of today's {sector['name']} news.",
        }

    except Exception as e:
        logger.error(f"Groq synthesis failed for {sector['name']}: {e}")
        raise
