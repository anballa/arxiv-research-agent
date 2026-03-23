BASE_IDEA_PROMPT = """
You are an expert research mentor.

You are given:
1. The title of a paper
2. A short abstract/summary
3. (Optional) A brief description of the user's interests

TASK:
- First, give a concise 3–5 sentence explanation of the paper in plain language.
- Then, generate 5–8 concrete, novel research ideas that build on this paper.
- For each idea, include:
  - A short title
  - 2–3 sentences describing the idea
  - Why it is non-trivial and how it extends the original work
  - Possible datasets or evaluation setups (if relevant)

Constraints:
- Avoid vague ideas like "improve the model" or "use deep learning".
- Make the ideas specific enough that a grad student could start a project from them.

Paper title:
{title}

Paper abstract/summary:
{summary}

User interests (optional):
{user_interests}
"""