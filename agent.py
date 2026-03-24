import os
import re
import textwrap
import time
import random
from datetime import datetime

import arxiv
import google.genai as genai
from google.api_core import exceptions as google_exceptions
from dotenv import load_dotenv

from prompts import BASE_IDEA_PROMPT

load_dotenv()

MODEL = "gemini-2.5-flash-lite"
OUTPUT_DIR = "outputs"


# ── Client ─────────────────────────────────────────────────────────────────

def configure_gemini() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
    return genai.Client(api_key=api_key)


# ── arXiv ──────────────────────────────────────────────────────────────────

def fetch_latest_paper(query: str) -> dict | None:
    time.sleep(2)  # arXiv rate-limit courtesy
    client = arxiv.Client()

    # Search title + abstract fields explicitly to avoid unrelated matches
    structured_query = f"ti:{query} OR abs:{query}"

    search = arxiv.Search(
        query=structured_query,
        max_results=5,
        sort_by=arxiv.SortCriterion.Relevance,  # relevance, not recency
    )

    results = list(client.results(search))
    if not results:
        print("❌ No papers found for that query.")
        return None

    # Show candidates and let the user pick
    print(f"\n  Found {len(results)} candidate(s):\n")
    for i, r in enumerate(results):
        authors = ", ".join(a.name for a in r.authors[:2])
        print(f"  [{i+1}] {r.title}")
        print(f"       {authors} — {r.published.strftime('%Y-%m-%d')}\n")

    if len(results) == 1:
        chosen = results[0]
    else:
        while True:
            raw = input(f"  Pick a paper [1–{len(results)}] or press Enter for #1: ").strip()
            if raw == "":
                chosen = results[0]
                break
            if raw.isdigit() and 1 <= int(raw) <= len(results):
                chosen = results[int(raw) - 1]
                break
            print("  Invalid choice, try again.")

    return {
        "title":   chosen.title,
        "summary": chosen.summary,
        "authors": [a.name for a in chosen.authors],
        "url":     chosen.entry_id,
    }


# ── Generation ─────────────────────────────────────────────────────────────

def generate_research_ideas(
    client: genai.Client,
    metadata: dict,
    user_interests: str = "",
) -> str:
    prompt = BASE_IDEA_PROMPT.format(
        title=metadata["title"],
        summary=metadata["summary"],
        user_interests=user_interests.strip() or "Not specified.",
    )

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            return response.text

        except (
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
        ) as e:
            wait = (2 ** attempt) + random.random()
            print(f"⚠️  {type(e).__name__}. Retrying in {wait:.1f}s...")
            time.sleep(wait)

        except Exception as e:
            print(f"❌ Non-retryable error: {e}")
            raise

    return "❌ Failed to generate ideas after 3 attempts."


# ── Output ─────────────────────────────────────────────────────────────────

def save_output(metadata: dict, ideas_text: str, query: str) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    slug = re.sub(r"[^\w]+", "_", query.strip().lower())[:40]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(OUTPUT_DIR, f"{slug}_{timestamp}.txt")

    authors = ", ".join(metadata["authors"][:3])
    if len(metadata["authors"]) > 3:
        authors += f" +{len(metadata['authors']) - 3} more"

    header = (
        f"Query:     {query}\n"
        f"Title:     {metadata['title']}\n"
        f"Authors:   {authors}\n"
        f"URL:       {metadata['url']}\n"
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"{'=' * 70}\n\n"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + ideas_text)

    return output_path


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("=== arXiv → Research Ideas Agent ===\n")

    query          = input("Enter arXiv search query: ").strip()
    user_interests = input("Describe your interests (optional): ").strip()

    # Validate API key before doing any network work
    client = configure_gemini()

    print("\n[1/3] Fetching latest paper from arXiv...")
    metadata = fetch_latest_paper(query)
    if not metadata:
        return

    print(f"\n  Title:   {metadata['title']}")
    print(f"  Authors: {', '.join(metadata['authors'][:3])}")
    print(f"\n  Abstract:\n")
    print(textwrap.fill(metadata["summary"], width=90, initial_indent="  ",
                        subsequent_indent="  "))

    print("\n[2/3] Generating research ideas with Gemini...")
    ideas_text = generate_research_ideas(client, metadata, user_interests)

    print("\n[3/3] Saving output...")
    output_path = save_output(metadata, ideas_text, query)
    print(f"  ✓ Saved to: {output_path}\n")


if __name__ == "__main__":
    main()