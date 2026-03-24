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
    """Initialize and return a Gemini API client.
    
    Returns:
        genai.Client: Configured Gemini client instance.
        
    Raises:
        RuntimeError: If GEMINI_API_KEY environment variable is not set.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")
    return genai.Client(api_key=api_key)


# ── arXiv ──────────────────────────────────────────────────────────────────

def fetch_latest_paper(query: str) -> dict | None:
    """Fetch relevant papers from arXiv and prompt user to select one.
    
    Args:
        query: Search query string for arXiv papers.
        
    Returns:
        dict: Metadata dict with keys (title, summary, authors, url), or None if no results.
        
    Raises:
        arxiv.ExhaustedException: If arXiv API fails after retries.
    """
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
        print(f"❌ No papers found for query: '{query}'")
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
            try:
                raw = input(f"  Pick a paper [1–{len(results)}] or press Enter for #1: ").strip()
                if raw == "":
                    chosen = results[0]
                    break
                if raw.isdigit() and 1 <= int(raw) <= len(results):
                    chosen = results[int(raw) - 1]
                    break
                print("  Invalid choice, try again.")
            except KeyboardInterrupt:
                print("\n  Selection cancelled.")
                return None

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
    """Generate research ideas based on a paper using Gemini API.
    
    Args:
        client: Gemini API client instance.
        metadata: Paper metadata dict with keys (title, summary, authors, url).
        user_interests: Optional user interests to tailor ideas.
        
    Returns:
        str: Generated research ideas text, or error message if generation fails.
        
    Raises:
        Exception: Non-retryable API errors are re-raised.
    """
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
        except (
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
        ) as e:
            wait = (2 ** attempt) + random.random()
            print(f"⚠️  {type(e).__name__} (attempt {attempt+1}/3). Retrying in {wait:.1f}s...")
            time.sleep(wait)

        except Exception as e:
            print(f"❌ Non-retryable error during idea generation: {type(e).__name__}: {e}")
            raise

    return "❌ Failed to generate ideas after 3 attempts."


# ── Output ─────────────────────────────────────────────────────────────────

def save_output(metadata: dict, ideas_text: str, query: str) -> str:
    """Save generated research ideas to a timestamped text file.
    
    Args:
        metadata: Paper metadata dict with keys (title, summary, authors, url).
        ideas_text: Generated research ideas text.
        query: Original search query.
        
    Returns:
        str: Path to the saved output file.
        
    Raises:
        OSError: If file writing fails.
    """
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
    except OSError as e:
        raise OSError(f"Failed to create output directory '{OUTPUT_DIR}': {e}")

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

    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + ideas_text)
    except IOError as e:
        raise OSError(f"Failed to write output file '{output_path}': {e}")

    return output_path


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point for the arXiv Research Ideas Agent.
    
    Orchestrates the workflow: prompt user for query, fetch paper from arXiv,
    generate research ideas using Gemini, and save results to file.
    """
    print("=== arXiv → Research Ideas Agent ===\n")

    # Get and validate user input
    query = input("Enter arXiv search query: ").strip()
    if not query:
        print("❌ Query cannot be empty. Exiting.")
        return
        
    user_interests = input("Describe your interests (optional): ").strip()

    # Validate API key before doing any network work
    try:
        client = configure_gemini()
    except RuntimeError as e:
        print(f"❌ Configuration failed: {e}")
        return

    print("\n[1/3] Fetching latest paper from arXiv...")
    try:
        metadata = fetch_latest_paper(query)
    except Exception as e:
        print(f"❌ Error fetching paper: {type(e).__name__}: {e}")
        return
        
    if not metadata:
        return

    print(f"\n  Title:   {metadata['title']}")
    print(f"  Authors: {', '.join(metadata['authors'][:3])}")
    print(f"\n  Abstract:\n")
    print(textwrap.fill(metadata["summary"], width=90, initial_indent="  ",
                        subsequent_indent="  "))

    print("\n[2/3] Generating research ideas with Gemini...")
    try:
        ideas_text = generate_research_ideas(client, metadata, user_interests)
    except Exception as e:
        print(f"❌ Error generating ideas: {type(e).__name__}: {e}")
        return

    print("\n[3/3] Saving output...")
    try:
        output_path = save_output(metadata, ideas_text, query)
        print(f"  ✓ Saved to: {output_path}\n")
    except OSError as e:
        print(f"❌ Error saving output: {e}")
        return


if __name__ == "__main__":
    main()