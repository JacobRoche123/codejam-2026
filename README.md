# ThinkLess

**Ask before thinking. Then use the smallest model that does the job.**

ThinkLess is a router that sits in front of an AI assistant. For every request it decides, for a fraction of a cent, whether the request is clear enough to answer and how much model it really needs, so simple questions stop being answered by the most expensive model.

Built in 24 hours at **CodeJam 16** (McGill University, November 2026) for the **Agent Solution** track: efficient use of compute, with a demo that shows *how* the agent decides, not just what it produces.

---

## The problem

Most AI apps send every request to their strongest model. "What is the capital of Australia?" and "Design a ride-sharing system for 50,000 users" get the same treatment and the same bill. On top of that, an assistant that misunderstands a vague request wastes a whole expensive answer.

## Why it matters

Every token a model generates runs through billions of parameters on a GPU. Doing less of that work saves four things at once.

```mermaid
flowchart LR
    A["Smaller model<br/>when it is enough"] --> C["Less GPU compute"]
    B["Fewer tokens<br/>(−27 % measured)"] --> C
    K["Cache hit<br/>(no model call)"] --> C
    C --> E["⚡ Less energy<br/>and emissions"]
    C --> M["💳 Lower bill<br/>(−60 % measured)"]
    C --> T["⏱ Faster answers"]
```

- **Compute and energy.** Smaller models do less computation per token, and fewer tokens means less computation overall. Research on AI inference shows energy use depends on model size and on how many tokens are generated ([Luccioni et al., *Power Hungry Processing*, ACM FAccT 2024](https://arxiv.org/abs/2311.16863)).
- **Tokens.** Measured: 27 % fewer tokens than sending everything to Opus, and tokens 40× cheaper whenever Haiku is enough.
- **Credits.** Measured: a 60 % lower bill on our benchmark. A question that was already answered costs nothing.
- **Time.** Small models answer faster, and a clarifying question avoids redoing a wrong answer.

**Ecological impact, stated honestly.** Less compute means less electricity and fewer emissions, but Anthropic does not publish energy figures per request, so we cannot convert our savings into watt-hours or grams of CO₂ without inventing numbers. We report what we can measure (tokens and cost) and treat it as the proxy for compute.

## How ThinkLess works

```mermaid
flowchart TD
    A[User request] --> B{Seen before?}
    B -- identical --> Z["Reuse earlier answer · $0"]
    B -- "≥ 75 % similar" --> C{"Haiku: same answer needed?"}
    C -- yes --> Z
    C -- no --> D
    B -- new --> D["Triage · Haiku 5.5"]
    D -- ambiguous --> Q["Ask up to 3 questions, once"]
    Q --> D
    D -- simple --> H["Haiku 5.5 · effort low"]
    D -- medium --> S["Sonnet 5.5 · effort medium"]
    D -- complex --> O["Opus 5.5 · effort high"]
```

1. **Cache.** An identical question is free. A similar one (text similarity ≥ 75 %) is checked by Haiku before reuse: "capital of France" and "capital of Germany" look 87 % alike but need different answers.
2. **Triage.** Claude Haiku 5.5 reads the request and returns a structured verdict: is anything essential missing, how hard is it, and a short brief for the model that will answer.
3. **Clarify.** If a missing detail would change the answer, ThinkLess asks at most 3 short questions, once. A question costs a fraction of a cent; a wrong expensive answer costs the whole call.
4. **Route.** The smallest sufficient model answers, with the original request (which always wins) plus the triage brief.
5. **Measure.** Every step records real token counts from the API and its cost.

The triage is an LLM, not keyword rules, because it understands meaning. Hard limits (max 3 questions, one round only, unknown tiers fall back to medium) are enforced in Python, because a prompt is a request, not a guarantee.

## Three ways to use it

```mermaid
flowchart LR
    U1["You, in a browser"] --> W["Demo app<br/>uv run thinkless"]
    U2["Any program"] --> R["Advisor API<br/>POST /api/route"]
    U3["An AI agent<br/>(Claude Code…)"] --> M["MCP tool<br/>choose_model"]
    W --> T(("ThinkLess<br/>triage"))
    R --> T
    M --> T
    T --> W2["Answer + every decision,<br/>tokens, cost, time"]
    T --> R2["Recommended model<br/>and effort, no answer"]
```

| Mode | What it does | Entry point |
|---|---|---|
| **Demo app** | Answers the request and shows every decision, its model, tokens, cost and time, next to "everything on Opus" | `uv run thinkless` → http://127.0.0.1:8000 |
| **Advisor API** | Returns the recommended model and effort, without answering; accepts your own list of models | `POST /api/route` |
| **MCP tool** | Plugs into Claude Code, Claude Desktop or any MCP agent as a `choose_model` tool, for any model family | `uv run thinkless-mcp` |
| **Claude Code plugin** | Routes **every** prompt automatically and delegates the work to a Haiku, Sonnet or Opus subagent: nothing to type | `claude plugin install thinkless@thinkless` |

## ThinkLess acts: automatic routing in Claude Code

With the plugin, ThinkLess is no longer an advisor you have to call: it runs on **every prompt** (a `UserPromptSubmit` hook) and the session's lead agent, **ThinkLess Router** (on Haiku), **delegates** the work to the subagent ThinkLess picked. Only hard tasks climb to Sonnet or Opus.

```mermaid
flowchart TD
    U["You type a request<br/>in Claude Code"] --> H["🪝 ThinkLess hook<br/>(automatic, every prompt)"]
    H -->|"triage · Haiku · ~0.02 ¢"| V{Difficulty}
    V -- simple --> L["Lead agent thinkless:router<br/>(Haiku) answers directly"]
    V -- medium --> M["Subagent thinkless:medium<br/>Sonnet · effort medium"]
    V -- complex --> O["Subagent thinkless:large<br/>Opus · effort high"]
    V -- ambiguous --> Q["Lead asks the user<br/>clarifying questions"]
```

**Measured in real Claude Code runs** (lead model Haiku, plugin loaded, Nov 2026; one run each, costs from Claude Code's own usage report):

| Prompt | ThinkLess decision | Models used | Cost |
|---|---|---|---|
| "What is the capital of Australia?" | simple | Haiku only | $0.003 |
| "Write a Python function that reads a CSV of expenses…" | medium → `thinkless:medium` | Haiku $0.004 + Sonnet $0.079 | $0.083 |
| "Design the architecture of a ride-sharing app for 50,000 students…" | complex → `thinkless:large` | Haiku $0.005 + Opus $0.204 | $0.210 |

For comparison, Claude Code running on Opus spent $0.11 to $0.13 on a five-bullet summary of the causes of the French Revolution, a task ThinkLess classified as simple in one run and medium in another (the triage is not perfectly consistent). These are single runs, not a benchmark: the [API benchmark](#results) is the controlled measurement.

**Why a dedicated lead agent.** With a plain Haiku session, the advice arrives as a note next to the prompt, and the lead sometimes ignores it: in an interactive test, Haiku received "medium → delegate to thinkless:medium" and wrote the code itself. Running the session as the `thinkless:router` agent puts the routing rule in the lead's **system prompt**, where it carries more weight. With the router, 5 out of 5 runs were routed as advised: 3 medium tasks went to Sonnet ($0.036 to $0.090 each), 1 complex task to Opus, and 1 simple question stayed on Haiku ($0.003).

**Install (Claude Code):**

1. Save your Anthropic API key in ThinkLess's own private file (the key is hidden while you paste it):

   ```bash
   mkdir -p ~/.config/thinkless && read -s "K?Paste your Anthropic API key: " && printf '%s' "$K" > ~/.config/thinkless/api_key && chmod 600 ~/.config/thinkless/api_key && unset K && echo
   ```

   Do **not** export `ANTHROPIC_API_KEY` in your shell for this: Claude Code itself would pick it up and switch from your subscription to API billing.

2. Add the marketplace and install the plugin:

   ```bash
   claude plugin marketplace add JacobRoche123/codejam-2026
   claude plugin install thinkless@thinkless
   ```

3. Start Claude Code with the ThinkLess Router as the lead agent, and work as usual:

   ```bash
   claude --agent thinkless:router
   ```

Turn the hook off for one session with `THINKLESS_HOOK=off claude`. Slash commands and replies under three words are never triaged. The hook runs in every Claude Code session once the plugin is enabled; to keep it only for the sessions you choose, disable the plugin (`claude plugin disable thinkless@thinkless`) and load it per session with `--plugin-dir`.

**Limits.** Delegation still depends on the lead model following its instructions: reliable with the router in our runs, not with a plain session (see above). The hook only sees the current message, not the conversation, so a short follow-up such as "step 6 problem" can be misjudged. Each subagent call carries Claude Code's own context, so a medium task costs more than in the raw API benchmark. The triage adds about 2 to 3 seconds per prompt.

## Install ThinkLess as an advisor tool (one command)

Anyone can add ThinkLess to their AI agent. It shows up as **"ThinkLess advisor"**, a read-only tool: it recommends a model and an effort level, and never answers or changes anything. No need to download the project.

> **New to the Terminal?** Follow the beginner guide: **[docs/INSTALL.md](docs/INSTALL.md)**. It says which app to open, what to type and what you should see at every step.

You need [uv](https://docs.astral.sh/uv/) (`brew install uv`, or see step 1 below) and your own [Anthropic API key](https://console.anthropic.com/): each piece of advice is one Claude Haiku call, about 0.02 cents, billed to your key.

```mermaid
flowchart LR
    U["Your agent<br/>(Claude Code, Cursor…)"] -->|"choose_model('prove √2 is irrational')"| T["ThinkLess advisor<br/>(runs on your computer)"]
    T -->|"one Haiku call<br/>with your key"| H(("Claude API"))
    T -->|"model: claude-opus-5-5<br/>effort: high<br/>reason: …"| U
```

**Claude Code** (tested):

```bash
claude mcp add thinkless --scope user -e ANTHROPIC_API_KEY=sk-ant-your-key -- uvx --from git+https://github.com/JacobRoche123/codejam-2026 thinkless-mcp
```

Check with `claude mcp list`, then ask Claude: *"Use the thinkless choose_model tool for: prove that √2 is irrational."*

**Claude Desktop, Cursor, Gemini CLI and other MCP clients** (same protocol, not tested): add this block to the client's MCP settings file (`claude_desktop_config.json`, `~/.cursor/mcp.json` or `~/.gemini/settings.json`), then restart the app:

```json
{
  "mcpServers": {
    "thinkless": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/JacobRoche123/codejam-2026", "thinkless-mcp"],
      "env": { "ANTHROPIC_API_KEY": "sk-ant-your-key" }
    }
  }
}
```

If a desktop app cannot find `uvx`, replace `"uvx"` with its full path (run `which uvx` in a terminal). If the key is missing or wrong, the tool tells the agent how to fix it.

---

## Results

All numbers below are **measured** from real API calls: token counts come from the Claude API, prices are Anthropic's published rates. Raw data is in [`bench/`](bench/).

### Router vs. "everything on Opus 5.5" (20 tasks)

```mermaid
xychart-beta
    title "Billed cost on 20 tasks (USD)"
    x-axis ["ThinkLess", "Opus for everything"]
    y-axis "USD" 0 --> 1
    bar [0.335, 0.845]
```

| | ThinkLess | Opus 5.5 for everything |
|---|---|---|
| Billed cost | **$0.335** | $0.845 |
| Tokens | **31,988** | 43,618 |
| Quality (judged /10) | **8.0** | 8.8 |

**60 % less billed compute, keeping 91 % of Opus's quality.**

How quality is judged: Claude Sonnet 5.5 grades both answers blind, **twice, with the order swapped**, and we average the scores to cancel position bias and noise. The 20 tasks mix simple facts, code, explanations, proofs, system design and 2 ambiguous requests ([`bench/tasks.json`](bench/tasks.json)).

We iterated three times, fixing what the benchmark revealed:

```mermaid
flowchart LR
    V1["v1 · first run<br/>−64 % cost<br/>quality 7.7 vs 8.5"] --> V2["v2 · executor sees the original request,<br/>judge runs twice<br/>−62 % · 7.8 vs 8.75 (89 %)"]
    V2 --> V3["v3 · stricter triage<br/>(code, rare facts → Sonnet)<br/>−60 % · 8.0 vs 8.8 (91 %)"]
```

### Thinking effort vs. model choice

Same model (Sonnet 5.5), same 6 tasks, three effort levels. Thinking tokens are billed as output, so fewer tokens means less compute.

```mermaid
xychart-beta
    title "Average output tokens by effort (Sonnet 5.5)"
    x-axis ["low", "medium", "high"]
    y-axis "tokens" 0 --> 1200
    bar [963, 967, 1110]
```

| Effort | Avg output tokens | vs. high | Quality vs. high |
|---|---|---|---|
| low | 963 | 87 % | 7.5 vs 8.4 |
| medium | 967 | 87 % | 8.1 vs 8.6 |
| high | 1,110 | 100 % | reference |

**Lowering effort saves about 13 % of tokens. Switching from Opus to Haiku cuts the price per token by 40×.** Choosing the right model is the main lever, which is why ThinkLess routes between models first.

### What we did not measure

- **Energy.** Anthropic does not publish per-request energy use, so we show no watt-hours. We use billed tokens and cost as the measurable proxy for compute: a bigger model costs more per token because it uses more compute per token.
- **A held-out test set.** The triage rules were tuned on the same 20 tasks they are scored on, so the numbers may be slightly optimistic. A fresh task set is the next thing to add.

---

## Limits

- **Advice, not control.** In the MCP and advisor modes, ThinkLess recommends a model; an agent cannot switch its own model mid-conversation. The advice pays off where the agent can delegate work, for example to a subagent.
- **Rare facts need big models.** Neither Haiku nor Sonnet knew what McGill's ECSESS is; only Opus did. Triage cannot always tell when a "simple" fact is actually obscure.
- **Prudence costs.** When unsure, triage picks the higher tier. That protects quality but sometimes overspends, for example sending a classic proof to Opus.
- **The triage can ignore its own rules.** It is instructed that answers with more than one line of code are "medium", and it sometimes still says "simple".
- **The similarity cache lives in memory** and misses paraphrases that share few words ("Where does Australia's government sit?").

---

## Step-by-step setup

ThinkLess is not a model: it is a small program that chooses between Claude models. You run it on your computer. Tested on macOS; Linux should work the same way.

```mermaid
flowchart TD
    S1["1 · Install uv"] --> S2["2 · Get an Anthropic API key"]
    S2 --> S3["3 · Download the project"]
    S3 --> S4["4 · Save the key in .env.local"]
    S4 --> S5["5 · Run the demo app"]
    S5 --> S6["6 · Optional: plug into Claude Code (MCP)"]
    S5 --> S7["7 · Optional: call the advisor API"]
```

**1. Install uv** (it installs the right Python version and the libraries for you):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

On a Mac with Homebrew, `brew install uv` works too. Open a new terminal afterwards.

**2. Get an Anthropic API key.** Create one at [console.anthropic.com](https://console.anthropic.com/) (Settings → API Keys). The API is billed by usage, separately from a Claude Pro subscription; trying the demo costs a few cents.

**3. Download the project:**

```bash
git clone https://github.com/JacobRoche123/codejam-2026.git
cd codejam-2026
```

**4. Save your key** in a file named `.env.local`. This command asks for the key without showing it on screen; the file is listed in `.gitignore`, so it is never published:

```bash
read -s "K?Paste your Anthropic API key: " && printf 'ANTHROPIC_API_KEY=%s\n' "$K" > .env.local && chmod 600 .env.local && unset K
```

(That is zsh, the default shell on macOS. In bash, use `read -s -p "Paste your key: " K` for the first part.)

**5. Start the demo app** and open http://127.0.0.1:8000:

```bash
uv run thinkless
```

Click the "Simple" example, tick "Compare with everything on Opus" and press "Send". The right column shows each decision, its model, tokens and cost. Stop the server with `Ctrl+C`.

**6. (Optional) Plug your local copy into Claude Code** as an MCP tool (to use the published version instead, see [Install ThinkLess as an advisor tool](#install-thinkless-as-an-advisor-tool-one-command)). Replace the path with where you cloned the project:

```bash
claude mcp add thinkless --scope user -- uv --directory /path/to/codejam-2026 run thinkless-mcp
```

Check it with `claude mcp list` (you should see `thinkless ... ✔ Connected`). Then start `claude` and ask, for example: *"Use the thinkless choose_model tool for: prove that √2 is irrational."* The demo server does not need to be running for this; Claude Code starts ThinkLess itself.

**7. (Optional) Ask the advisor over HTTP**, like any program could (needs the server from step 5):

```bash
curl -s -X POST http://127.0.0.1:8000/api/route \
  -H "Content-Type: application/json" \
  -d '{"request": "Translate hello into Spanish"}'
```

## Which agents can use it?

ThinkLess speaks the [Model Context Protocol](https://modelcontextprotocol.io/) (MCP), the open standard many AI agents use to plug in tools. It currently runs as a **local** MCP server: the agent starts it on your computer and talks to it over stdio.

```mermaid
flowchart LR
    T["ThinkLess<br/>local MCP server (stdio)"]
    T --> A1["✅ Claude Code<br/>tested, works"]
    T --> A2["🟡 Claude Desktop · Cursor ·<br/>VS Code (Copilot) · Gemini CLI<br/>same protocol, not tested"]
    T -.-> A3["❌ ChatGPT web app<br/>needs a hosted HTTP version<br/>with authentication"]
```

### Works with any model family

ThinkLess judges **how hard a task is**, which does not depend on the provider. An agent can send **its own models**, ordered from smallest/cheapest to largest, and the advice then names one of them:

```mermaid
flowchart LR
    R["Request"] --> T["Triage<br/>simple · medium · complex"]
    T --> S["small → first model"]
    T --> M["medium → middle model<br/>(the larger of two middles)"]
    T --> L["large → last model"]
```

```bash
curl -s -X POST http://127.0.0.1:8000/api/route \
  -H "Content-Type: application/json" \
  -d '{"request": "Prove that √2 is irrational", "available_models": ["small-model", "medium-model", "large-model"]}'
```

```json
{"tier": "complex", "size": "large", "model": "large-model", "effort": "high", "source": "your list"}
```

The MCP tool takes the same optional `available_models` argument, and its description tells agents to pass their models. Without a list, ThinkLess recommends Claude models (Haiku, Sonnet, Opus). The `effort` field (low, medium, high) is a hint: use your provider's closest setting, if it has one.

**Still required:** the triage itself runs on Claude Haiku, so an Anthropic API key is needed whatever the agent. Next steps to remove that: other triage backends, or MCP *sampling* (letting the agent's own model do the triage), which few clients support today.

## Tests and benchmarks

Run the tests (offline, free, with a fake model):

```bash
uv run pytest -q          # 54 tests
```

Reproduce the benchmarks (real API calls, about $1.60 and $0.80):

```bash
uv run python bench/run.py
cd bench && uv run python effort.py
```

## Architecture

```mermaid
flowchart TD
    UI["web/ · demo page"] -->|HTTP| SV["server.py<br/>/api/ask · /api/route"]
    AG["AI agent"] -->|MCP stdio| MC["mcp_server.py<br/>choose_model"]
    SV --> PL["pipeline.py<br/>Router.ask · Router.route"]
    MC --> PL
    PL --> CA["cache.py<br/>similarity + Haiku check"]
    PL --> TR["triage.py<br/>prompt, schema, guardrails"]
    PL --> CF["config.py<br/>tiers, prices, cost"]
    CA --> LL["llm.py<br/>only file that calls the API"]
    TR --> LL
    PL --> LL
    LL --> API(("Claude API"))
```

| File | Role |
|---|---|
| [`src/thinkless/config.py`](src/thinkless/config.py) | Model tiers, published prices, thresholds, cost formula |
| [`src/thinkless/llm.py`](src/thinkless/llm.py) | The only file that calls the Claude API (swappable for a fake in tests) |
| [`src/thinkless/triage.py`](src/thinkless/triage.py) | Triage prompt, structured-output schema, Python guardrails |
| [`src/thinkless/cache.py`](src/thinkless/cache.py) | Text similarity + Haiku confirmation |
| [`src/thinkless/pipeline.py`](src/thinkless/pipeline.py) | `Router.ask` (full answer) and `Router.route` (advice only), with per-step tracing |
| [`src/thinkless/server.py`](src/thinkless/server.py) | FastAPI: `/api/ask`, `/api/route`, `/api/benchmark` |
| [`src/thinkless/mcp_server.py`](src/thinkless/mcp_server.py) | MCP server exposing `choose_model` |
| [`src/thinkless/hook.py`](src/thinkless/hook.py) | Claude Code hook: triages every prompt and tells Claude which subagent to use |
| [`plugin/`](plugin/) | Claude Code plugin: the hook, the MCP server, the `router` lead agent and the `small`, `medium`, `large` subagents |
| [`web/`](web/) | Demo page: live trace, benchmark tab, how-it-works |
| [`bench/`](bench/) | Tasks, benchmark scripts and raw results |
| [`tests/`](tests/) | 54 offline tests |

**Stack:** Python 3.12, Anthropic Python SDK, FastAPI, MCP Python SDK, vanilla HTML/CSS/JS. Models: Claude Haiku 5.5, Sonnet 5.5 and Opus 5.5.

---

Built by Jacob Roche at CodeJam 16, with Claude Code as a pair programmer.
