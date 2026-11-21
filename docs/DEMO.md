# ThinkLess: 2-minute demo script

Spoken text is in quotes. Actions are in **bold**. Aim for about 260 spoken words (2 minutes at a calm pace).

---

## Before you go on stage (5 minutes)

1. **Restart the server** so the cache starts empty: `Ctrl+C`, then `uv run thinkless`.
2. Open http://127.0.0.1:8000 on the **Live demo** tab. Zoom the browser to 125–150 % so the jury can read it.
3. Click the **Benchmark** tab once so it is loaded, then go back to **Live demo**.
4. Have the Claude Code screenshot (ThinkLess called through MCP) open in another window.
5. Keep these two questions in a note, ready to paste:
   - `What is the capital city of Australia?`
   - `What is the capital of Austria?`
6. Check the Wi-Fi. If it is down, use Plan B (end of this page).

---

## The script

### 0:00 – 0:15 · The hook (no clicking)

"Every AI app sends *'What's the capital of Australia?'* to its most expensive model. That wastes money, time and the energy behind every token. **ThinkLess** asks before thinking, then uses the smallest model that does the job."

### 0:15 – 0:40 · Demo 1: a simple question

**Click "Simple", tick "Compare with everything on Opus", click Send.**

"First, a cheap model, Haiku, triages the request for a fraction of a cent. It says: simple fact, Haiku is enough. On the right you see every step, with real tokens and cost from the API. And for comparison, the same question on Opus: about ten times more expensive, for the same answer."

**Point at the "−90 %" in the summary.**

### 0:40 – 1:00 · Demo 2: a vague request

**Click "Ambiguous", untick "Compare", click Send.**

"Now a vague request: *write me a script to sort my files.* Instead of guessing, ThinkLess asks: which language, which criteria, which system? A question costs a fraction of a cent. A wrong answer costs the whole call."

(Do not answer the questions: move on.)

### 1:00 – 1:20 · Demo 3: the smart cache

**Paste `What is the capital city of Australia?` and Send.**

"A rephrased question: 93 % similar, Haiku confirms it's the same question, so we reuse the answer."

**Paste `What is the capital of Austria?` and Send.**

"Now *Austria*: 97 % similar text, but a different country. Haiku rejects the match. Text similarity alone would have answered *Canberra*."

### 1:20 – 1:45 · The numbers

**Click the Benchmark tab.**

"We measured this on 20 tasks, graded blind by another model, twice, with the order swapped. ThinkLess uses **60 % less billed compute** and **27 % fewer tokens**, while keeping **91 % of Opus's quality**. We also found that lowering the thinking effort only saves 13 % of tokens: choosing the right model is the real lever."

### 1:45 – 1:55 · It plugs into real agents

**Show the Claude Code screenshot.**

"And ThinkLess is an MCP tool: here, Claude Code asks it which model to use before working."

### 1:55 – 2:00 · Close

"ThinkLess: think less, waste less. Thank you!"

---

## Plan B (no internet or the API is slow)

- The **Benchmark** tab works offline: it reads local results. Start there and tell the story with the numbers.
- Show the Claude Code screenshot for the MCP part.
- Best of all: record this script as a video beforehand (Devpost usually asks for one anyway), and play it if the live demo fails.

---

## Likely jury questions

**"Where does the 60 % come from?"**
"We ran 20 tasks two ways: through ThinkLess, and everything on Opus 5.5. The API returns the exact token counts; we multiply them by Anthropic's published prices. ThinkLess cost $0.335, Opus alone $0.845. That's 60 % less."

**"How do you measure quality? Isn't it biased to let an AI grade an AI?"**
"A bit, yes, so we reduced the bias: the judge doesn't know which answer is which, and it grades every pair twice with the order swapped, then we average. It's not perfect, and we say so. A human evaluation would be the next step."

**"Why use an AI for the triage instead of simple rules?"**
"Keywords fail on meaning: *'prove you're listening'* isn't a math proof. Haiku understands the request, and it's cheap: the triage is roughly 1 % of our bill (estimate). The hard limits, like at most three questions, are enforced in Python, because a prompt is a request, not a guarantee."

**"What if the triage picks a model that's too small?"**
"It happens: our benchmark shows Haiku failing on a regex detail and on a rare fact. So when it's unsure, the triage picks the bigger model, and we added rules for detail-critical and niche tasks. That's the trade-off: a bit less savings for more quality."

**"How much energy or CO₂ do you save?"**
"We can't give an honest number: Anthropic doesn't publish energy per request. What we measure is tokens and cost, which follow compute. Research shows energy depends on model size and tokens generated, so fewer tokens on smaller models means less energy, but we won't invent watt-hours."

**"Did you tune your rules on the same tasks you tested?"**
"Yes, and it's a real limit: the numbers may be slightly optimistic. The next step is a fresh set of tasks the rules have never seen."

**"Does it work with ChatGPT or Gemini?"**
"It's a local MCP server. Claude Code works, tested. Other local MCP clients, like Gemini CLI or Cursor, use the same protocol but I haven't tested them. ChatGPT mostly needs remote servers, so we'd have to host ThinkLess online with authentication. And the tiers would need mapping to their models."

**"Can an agent actually switch models with your advice?"**
"Not by itself mid-conversation: ThinkLess advises, it doesn't control. The advice pays off where the agent can delegate, for example to a subagent on the recommended model."

**"Why does the cache need Haiku? Isn't the similarity score enough?"**
"Austria versus Australia: 97 % similar, different answers. And 'France' versus 'Germany' scored higher than two real paraphrases. A threshold alone would serve wrong answers."

**"Did you use AI to build this?"**
"Yes, Claude Code as a pair programmer, and as a teacher. I'm a first-year student at my first hackathon, so I asked it to explain every file, and I ran experiments myself until I could explain the whole data flow, which is what I just did."

**"What would you do with more time?"**
"Host it online for other agents, map the tiers to other providers, a fresh benchmark, and a cache that survives restarts."
