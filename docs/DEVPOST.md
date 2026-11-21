# Devpost submission: ThinkLess

Copy each section into the matching Devpost field.
Lines starting with ✏️ are notes for you: personalize or delete them before submitting.

---

## Project name

ThinkLess

## Tagline

Ask before thinking, then use the smallest AI model that does the job.

## Track

Agent Solution (efficient use of compute, clear demo of how the agent works)

## Built with

python · fastapi · anthropic · claude · model-context-protocol · mcp · javascript · html · css · mermaid · uv · pytest

## Links

- GitHub: https://github.com/JacobRoche123/codejam-2026
- Demo video: ✏️ add the link once recorded (2 minutes max)

---

## Inspiration

Most AI apps send every request to their strongest model. "What's the capital of Australia?" gets the same expensive treatment as "design a system for 50,000 users". That wastes money, time and the energy behind every token. I wanted an agent that thinks about how much thinking a request deserves, and that asks a quick question instead of confidently answering the wrong thing.

✏️ Add one personal sentence: a moment where you noticed this waste yourself, or why efficiency matters to you.

## What it does

ThinkLess is a router that sits in front of an AI assistant. For every request it:

1. **Checks its memory.** An identical question costs nothing. A similar one (text similarity ≥ 75 %) is double-checked by a small model before reuse, because "capital of France" and "capital of Germany" look 87 % alike but need different answers.
2. **Triages** the request with Claude Haiku 5.5, the cheapest model, for about 0.02 cents: is anything essential missing, and how hard is it?
3. **Asks** up to 3 short clarifying questions when a missing detail would change the answer.
4. **Routes** to the smallest model that should be enough: Haiku for simple facts, Sonnet for code and explanations, Opus for proofs and system design.
5. **Measures** every step with real token counts and cost, and shows it live next to "what if everything went to Opus".

It works three ways: a demo web app that shows every decision, an advisor API that returns only the recommended model, and an **MCP tool** that plugs into AI agents like Claude Code, so an agent can ask ThinkLess which model to use before it starts working.

**Measured on 20 tasks, graded blind:** 60 % less billed compute and 27 % fewer tokens than sending everything to Opus, while keeping 91 % of its quality.

## How I built it

- **Python + FastAPI** for the server, plain HTML/CSS/JavaScript for the demo page.
- **Anthropic's Claude API** for the three models. The triage uses structured outputs (a JSON schema), so the model must answer in a fixed format the code can trust.
- **Guardrails in Python** on top of the prompt: at most 3 questions, a single round, safe defaults. A prompt is a request; code is a guarantee.
- **A similarity cache** built in two layers: free text similarity with Python's `difflib`, then a Haiku check only when the texts look close.
- **The MCP Python SDK** to expose ThinkLess as a tool that agents can call.
- **A benchmark** of 20 tasks: each runs through ThinkLess and through Opus alone, and Claude Sonnet grades both answers blind, twice with the order swapped. A second benchmark compares thinking-effort levels.
- **26 offline tests** with a fake model, so the logic is checked for free in under a second.

I built it with Claude Code as a pair programmer, and used it as a teacher too: I asked it to explain every file, then did small experiments myself (changing prices, breaking a test on purpose, predicting results) until I could explain the whole data flow on my own.

## Challenges I ran into

- **The router changed the question.** In my first benchmark, a request asked "positive or negative?" and the triage rewrote it as "positive, negative or mixed", so the cheap model gave a different answer and lost points. Fix: the answering model always sees the original request, and the triage only adds notes.
- **The judge was noisy.** The same answer scored 4/10 once and 8/10 when re-run. I switched to grading twice with the answers swapped and averaging.
- **A similarity threshold alone cannot work.** "Capital of France" vs "capital of Germany" scored higher (87 %) than two real paraphrases (82 %). That is why the cache asks a model to confirm.
- **Rare facts.** Neither Haiku nor Sonnet knew what McGill's ECSESS is; only Opus did. Some "simple" questions are not simple for small models.
- **Debugging basics**, like an old server still holding port 8000 and returning "Method Not Allowed" for a route that existed in the new code.

## Accomplishments that I'm proud of

- Real, reproducible numbers instead of claims: three benchmark versions (v1 → v3), each fixing what the previous one revealed.
- Being honest about limits: no invented energy figures, a list of what the router gets wrong, and which agents are tested versus untested.
- ThinkLess running inside a real agent (Claude Code) through MCP.
- Understanding my own project well enough to explain every step, as a first-year student at my first hackathon.

## What I learned

- Choosing the right **model** matters far more than lowering **effort**: lower effort saved about 13 % of tokens, while Haiku is 40× cheaper per token than Opus.
- An AI's instructions are requests, not guarantees; important rules belong in code.
- How to measure before claiming, and how to separate what is measured from what is estimated.
- New tools and concepts: APIs and JSON, HTTP servers, tests with a fake model, structured outputs, threads, MCP, and Git branches.

✏️ Add the one thing that surprised you most this weekend, in your own words.

## What's next for ThinkLess

- **Host it online** (MCP over HTTP, with authentication and rate limits) so agents that need remote tools, like ChatGPT, can use it.
- **Provider-neutral tiers**: map simple/medium/complex to other providers' small, medium and large models.
- **A held-out benchmark** of fresh tasks, since the triage rules were tuned on the same 20 tasks.
- **A persistent cache** that survives restarts, and smarter paraphrase matching.

---

✏️ Before submitting: check CodeJam's rules on AI tools and make sure this AI-assistance statement matches them.
