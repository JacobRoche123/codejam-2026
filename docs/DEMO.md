# ThinkLess: demo script (4 minutes + questions)

Spoken text is in quotes. Actions are in **bold**. About 500 spoken words: 4 minutes at a calm pace, leaving a margin inside the 3 to 5 minute slot.

---

## Before you go on stage (10 minutes)

**Window 1: the demo app**

1. In a terminal: `cd ~/codejam-2026 && uv run thinkless` (restarting it empties the cache, which the cache demo needs).
2. Open http://127.0.0.1:8000 on the **Live demo** tab, zoom the browser to 125–150 %.
3. Click the **Benchmark** tab once so it loads, then go back to **Live demo**.

**Window 2: Claude Code with the plugin**

4. Clear the plugin's answer cache, so the demo request is not already cached: `rm -f ~/.config/thinkless/cache.json`.
5. In a second terminal: `cd ~/codejam-2026 && claude --agent thinkless:router`. Check that the header says **Haiku 5.5** and **@thinkless:router**.
6. Send one warm-up message, for example `What is the capital of Canada?`, so the hook is downloaded and fast, and check that the answer starts with "(ThinkLess: … · saved so far: …)". Then type `/clear` to start clean.
7. Make the terminal font large (⌘ +).

**Window 3: the savings page**

8. In a third terminal: `uvx --from git+https://github.com/JacobRoche123/codejam-2026 thinkless-savings`. Keep the page it opens in a browser tab, and the terminal ready to run it again.

**Ready to paste (keep them in a note):**

- `What is the capital city of Australia?`
- `What is the capital of Austria?`
- `Write a Python function that groups a list of course codes like COMP-251 by department and counts them`

**Check:** Wi-Fi works. If not, use Plan B at the end of this page.

---

## The script

### 0:00 – 0:20 · The hook (no clicking)

"Every AI app sends *'What's the capital of Australia?'* to its most expensive model. That wastes money, time and the energy behind every token. **ThinkLess** is an agent that thinks about how much thinking a request deserves. It asks before thinking, then uses the smallest model that does the job."

### 0:20 – 0:50 · Demo 1: a simple question (window 1)

**Click "Simple", tick "Compare with everything on Opus", click Send.**

"First, Haiku, the cheapest model, triages the request for a fraction of a cent: simple fact, Haiku is enough. On the right, every step with real tokens and real cost from the API. And for comparison, the same question on Opus: about ten times more expensive for the same answer."

**Point at the "−90 %" in the summary.**

### 0:50 – 1:10 · Demo 2: a vague request

**Click "Ambiguous", untick "Compare", click Send.**

"A vague request: *write me a script to sort my files*. Instead of guessing, ThinkLess asks: which language, which criteria, which system? A question costs a fraction of a cent. A wrong answer costs the whole call."

### 1:10 – 1:35 · Demo 3: the smart cache

**Paste `What is the capital city of Australia?` and Send.**

"Rephrased: 93 % similar, Haiku confirms it's the same question, so we reuse the answer."

**Paste `What is the capital of Austria?` and Send.**

"*Austria*: 97 % similar text, but a different country. Haiku rejects the match. Text similarity alone would have answered *Canberra*."

### 1:35 – 2:05 · The numbers

**Click the Benchmark tab.**

"We measured it on 20 tasks, graded blind by another model, twice, with the order swapped: **60 % less billed compute**, **27 % fewer tokens**, keeping **91 % of Opus's quality**. And one surprise: lowering the thinking effort saves only 13 % of tokens. Choosing the right model is the real lever."

### 2:05 – 3:15 · ThinkLess acts: inside a real agent (window 2)

**Switch to Claude Code. Point at the header.**

"Now the agent part. This is Claude Code, a real coding agent, with the ThinkLess plugin. The lead agent runs on **Haiku**, the cheap model. No API key, no special command."

**Paste the course-codes request and press Return.**

"ThinkLess decides this needs Claude Sonnet 5.5, so the lead **delegates** it. Look: `thinkless:sonnet`. Haiku didn't do the work, and Opus was never called."

**While it runs (about 15 seconds):**

"For a hard task, like designing a system, it goes to Opus. For a simple one, Haiku answers alone for three tenths of a cent. A cheap lead, and the big models only when the task deserves it."

**When the answer arrives, point at its first line.**

"Every answer says which model did the work, and this counter: how much ThinkLess has saved so far compared with Opus."

### 3:15 – 3:45 · The cache and the savings report

**Paste the same course-codes request again and press Return.**

"Same question again: ThinkLess recognizes it and reuses the answer. No Sonnet call at all: in our test, 2.46 cents the first time, 0.25 the second."

**Switch to window 3 and run `thinkless-savings`, or show the page you opened before.**

"And this page reads Claude Code's own logs, with no API call: every prompt, the model used, what it cost, and what the same work would have cost on Opus."

### 3:45 – 4:00 · Close

"ThinkLess: think less, waste less. Real measurements, real limits documented, and an agent anyone can install today, with no API key. Thank you!"

---

## If you are running short (3-minute version)

Cut demo 2 (vague request) and shorten the numbers to one sentence: "60 % less compute, 91 % of the quality, measured blind on 20 tasks."

## Plan B (no internet, or the API is slow)

- The **Benchmark** tab works offline: it reads local results. Tell the story with the numbers.
- Show screenshots of Claude Code delegating to `thinkless:sonnet` and `thinkless:opus`.
- Best: record the whole demo as a video beforehand (Devpost usually asks for one) and play it if the live demo fails.

---

## Likely jury questions

**"Where does the 60 % come from?"**
"We ran 20 tasks two ways: through ThinkLess, and everything on Opus 5.5. The API returns exact token counts; we multiply by Anthropic's published prices. $0.335 versus $0.845: 60 % less."

**"How do you measure quality? Isn't it biased to let an AI grade an AI?"**
"A bit, so we reduced the bias: the judge doesn't know which answer is which, grades every pair twice with the order swapped, and we average. A human evaluation would be the next step."

**"Why an AI for the triage instead of simple rules?"**
"Keywords fail on meaning. Haiku understands the request, for a fraction of a cent. And the hard limits, like at most three questions, are enforced in Python, because a prompt is a request, not a guarantee."

**"Does the lead model always follow the advice?"**
"Not by default: in a plain Haiku session, it once received 'delegate to Sonnet' and wrote the code itself. So we made a dedicated lead agent whose system prompt is the routing rule. With it, 5 out of 5 test runs were routed as advised, and we tested it live in an interactive session. A model follows its system prompt more reliably than a note next to the message."

**"Why Haiku as the lead, not Opus?"**
"Every message passes through the lead. If the lead is Opus, you already pay Opus prices before delegating, and in our tests Opus preferred to answer itself. A cheap lead that escalates only hard tasks is how production systems do it."

**"What if the triage picks a model that's too small?"**
"It happens: Haiku missed a regex detail and a rare fact in our benchmark. When unsure, the triage picks the bigger model, and we added rules for detail-critical and niche tasks. A bit less savings for more quality."

**"How much energy or CO₂ do you save?"**
"We can't give an honest number: Anthropic doesn't publish energy per request. We measure tokens and cost, which follow compute. Research shows energy depends on model size and tokens generated, so fewer tokens on smaller models means less energy, but we won't invent watt-hours."

**"Did you tune your rules on the same tasks you tested?"**
"Yes, and it's a real limit: the numbers may be slightly optimistic. [If done: 'So we also tested once on 10 tasks it had never seen: X % savings, Y % of the quality.']"

**"Does it work with ChatGPT or Gemini?"**
"The advice works for any provider: an agent sends its own model list and ThinkLess picks one. As a tool, it runs as a local MCP server: Claude Code is tested; Gemini CLI and Cursor use the same protocol but are untested. ChatGPT needs a hosted online version with authentication: that's our next step."

**"What does the hook see?"**
"Only the current message, not the conversation. So a short follow-up like 'step 6 problem' can be misjudged. Reading the recent conversation before triaging is an improvement we'd add next."

**"How can it work without an API key?"**
"The lead agent runs on Haiku inside your Claude plan, and its system prompt holds the routing rules, so it decides the model itself. With a key, a dedicated triage call with a fixed answer format and hard limits in code decides instead, for two hundredths of a cent per message. Without a key, it's free in API credits, but it still uses a little of your plan's usage."

**"Isn't reusing an answer dangerous?"**
"It can be, so the cache is strict: same project, last 24 hours, at least 85 % similar, and the lead checks that the question is really the same and doesn't depend on files that changed. 'Capital of Austria' versus 'capital of Australia' is 97 % similar text and must not be reused. And it only saves money when it avoids a Sonnet or Opus call."

**"Where does the counter come from? Is it real?"**
"It reads Claude Code's own logs: the exact tokens each model used. The actual cost is measured. The Opus side is an estimate: the same tokens priced as Opus, since we didn't actually run Opus. On a subscription these are API-equivalent amounts, so the saving is plan usage, not dollars. And when a task really needs Opus, ThinkLess costs slightly more, about 3 %, because of the Haiku lead; the report shows that too."

**"Did you use AI to build this?"**
"Yes, Claude Code as a pair programmer and as a teacher. It's my first hackathon, so I asked it to explain every file and ran experiments myself until I could explain the whole data flow, which is what I just did."

**"What would you do with more time?"**
"Host it online for ChatGPT and other agents, a triage that doesn't need an Anthropic key, triage with conversation context, and a larger benchmark with fresh tasks."
