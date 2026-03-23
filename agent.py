import os
import textwrap
import arxiv
import time
import random
from prompts import BASE_IDEA_PROMPT
from dotenv import load_dotenv
import google.genai as genai
from google.api_core import exceptions # Needed for error catching

load_dotenv()

def configure_gemini():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in your environment.")
    # Use the 2026 SDK Client
    client = genai.Client(api_key=api_key)
    return client

def fetch_latest_paper(query: str):
    # Politeness: arXiv asks for a delay between calls
    time.sleep(2) 
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=1,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )
    
    try:
        result = next(client.results(search))
        return {
            "title": result.title,
            "summary": result.summary,
            "authors": [a.name for a in result.authors],
        }
    except StopIteration:
        print("❌ No papers found for that query.")
        return None

def generate_research_ideas(client, metadata, user_interests: str = "") -> str:
    prompt = BASE_IDEA_PROMPT.format(
        title=metadata["title"],
        summary=metadata["summary"],
        user_interests=user_interests or "Not specified.",
    )

    # RETRY LOGIC for "Too Many Requests"
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt
            )
            return response.text
        except Exception as e:
            # If rate limited, wait and try again
            wait = (2 ** attempt) + random.random()
            print(f"⚠️ Rate limited or Error. Retrying in {wait:.1f}s...")
            time.sleep(wait)
    
    return "Failed to generate ideas after multiple attempts."

def main():
    print("=== arXiv -> Research Ideas Agent ===\n")
    query = input("Enter arXiv search query: ")
    user_interests = input("Describe your interests (optional): ")

    print("\n[1/3] Fetching latest paper from arXiv...")
    metadata = fetch_latest_paper(query)
    
    if not metadata: return

    print(f"\nTitle: {metadata['title']}\n")
    print("Abstract:\n")
    print(textwrap.fill(metadata["summary"], width=90))

    print("\n[2/3] Generating research ideas with Gemini...")
    client = configure_gemini()
    ideas_text = generate_research_ideas(client, metadata, user_interests)

    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", "research_ideas.txt")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ideas_text)

    print("\n[3/3] Done.")
    print(f"Ideas saved to: {output_path}")

if __name__ == "__main__":
    main()