# ThinkLess

**Ask before thinking. Then use the smallest Claude model that does the job.**

ThinkLess is a plugin for Claude Code that acts as a conductor. Before any work starts, it decides which Claude model your request really needs: **Claude Haiku 5.5** for simple questions, **Claude Sonnet 5.5** for everyday code and explanations, **Claude Opus 5.5** for hard reasoning and system design, and, rarely, **Claude Fable 5.2** for research-level work. A fast Haiku lead answers the simple requests itself, hands everything else to the model it named, and reuses an earlier answer when you ask the same question again, so you stop spending top-model compute on easy or repeated work. It needs **no API key**: it runs inside your Claude plan. Every answer shows which model did the work and a live counter of what ThinkLess has saved so far, and one command opens a report of your savings read from Claude Code's own logs. On our 20-task benchmark, routing cut the API-equivalent cost by **60 %** and used **27 % fewer tokens** than sending everything to Opus, while keeping **91 % of its quality** (graded blind). Fewer tokens on smaller models also means less computation on GPUs, so less electricity and fewer emissions behind each answer; we do not convert that into watt-hours, because Anthropic does not publish energy figures per request.

| Your request looks like… | ThinkLess picks |
|---|---|
| A fact, a translation, a short rewrite | Claude Haiku 5.5 · effort low |
| Code, a multi-step explanation, a summary, a plan | Claude Sonnet 5.5 · effort medium |
| Hard reasoning, a proof, system design with trade-offs | Claude Opus 5.5 · effort high |
| Research-level work (rare) | Claude Fable 5.2 · effort high |
| Something vague | Up to 3 short questions first |
| The same question as earlier in this project | The earlier answer, reused |

Every answer starts with a line like this:

```text
(ThinkLess: Claude Sonnet 5.5 · saved so far: $1.43 vs Opus 5.5 (−40 %) over 25 prompts)
```

---

## Install in Claude Code (Mac, about 10 minutes)

You need a Claude plan that includes Claude Code. An Anthropic API key is **optional**.

### 1. Open the Terminal

Press **⌘ Space**, type **Terminal**, press **Return**. Type every command below on the line that ends with `%`, then press **Return** and wait for the `%` to come back.

### 2. Install uv (runs ThinkLess for you)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Quit the Terminal (**⌘ Q**) and open it again. Check with `uvx --version`: you should see a version number.

### 3. Install Claude Code (skip if you have it)

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Quit and reopen the Terminal, type `claude`, sign in with your Claude account in the browser window that opens, then type `/exit`.

### 4. Install the plugin

```bash
claude plugin marketplace add JacobRoche123/codejam-2026
```

```bash
claude plugin install thinkless@thinkless
```

You should see two success messages. Check with `claude plugin list`: **thinkless** is listed and enabled.

### 5. Start Claude Code with the ThinkLess conductor

```bash
claude --agent thinkless:router
```

The header shows **Haiku 5.5** and **@thinkless:router**. The first message can take a few extra seconds while ThinkLess downloads.

### 6. Use Claude as usual

Try these and watch the opening line of each answer:

| Type this | You should see |
|---|---|
| `What is the capital of Australia?` | "(ThinkLess: Claude Haiku 5.5 · saved so far: …)" and an instant answer |
| `Write a Python function that reads a CSV of expenses and returns the total per category, skipping invalid lines` | A **thinkless:sonnet** block, then "(ThinkLess: Claude Sonnet 5.5 · …)" and the code |
| `Design the architecture of a ride-sharing app for 50,000 students, with the main trade-offs` | A **thinkless:opus** block (about a minute), then the full design |
| The CSV request again, word for word | "(ThinkLess: reused a previous answer · …)": no Sonnet call this time |

### 7. See your savings

```bash
uvx --from git+https://github.com/JacobRoche123/codejam-2026 thinkless-savings
```

It prints a summary and opens a page in your browser with every prompt ThinkLess routed: models used, actual cost, the same work priced as Opus 5.5, and the saving. It makes no API call: it only reads Claude Code's logs on your Mac.

---

## Optional: precise triage with an API key

Without a key, the Haiku lead decides the model itself, inside your Claude plan. With an Anthropic API key, a dedicated triage step (Claude Haiku with a fixed answer format and hard limits in code) decides instead, for about 0.02 cents per message billed to that key. Create a key at [console.anthropic.com](https://console.anthropic.com/) (Settings → API Keys, add a little credit under Billing), then run this and paste the key when asked (nothing appears while you paste):

```bash
mkdir -p ~/.config/thinkless && read -s "K?Paste your Anthropic API key: " && printf '%s' "$K" > ~/.config/thinkless/api_key && chmod 600 ~/.config/thinkless/api_key && unset K && echo "Key saved"
```

Do not export it as `ANTHROPIC_API_KEY` in your shell: Claude Code would then bill your API key instead of your Claude plan.

---

## Everyday commands

| To… | Run |
|---|---|
| See your savings | `uvx --from git+https://github.com/JacobRoche123/codejam-2026 thinkless-savings` |
| Update ThinkLess | `claude plugin marketplace update thinkless` then `claude plugin update thinkless@thinkless` |
| Hide the counter for one session | `THINKLESS_COUNTER=off claude --agent thinkless:router` |
| Skip ThinkLess's hook for one session | `THINKLESS_HOOK=off claude` |
| Clear the answer cache | `rm ~/.config/thinkless/cache.json` |
| Turn ThinkLess off everywhere | `claude plugin disable thinkless@thinkless` |
| Uninstall | `claude plugin uninstall thinkless@thinkless` |

## If something goes wrong

| You see | Do this |
|---|---|
| `command not found: claude` or `uvx` | Quit and reopen the Terminal; if it persists, redo step 2 or 3 |
| No "(ThinkLess: …)" line, no **thinkless:sonnet** block | Check that the header says **@thinkless:router**; restart with `claude --agent thinkless:router` |
| The counter is missing | The first answer after installing can come before the counter is ready; ask again. Also check `THINKLESS_COUNTER` is not set to `off` |
| "ThinkLess hook skipped" | Run `claude plugin update thinkless@thinkless`; if you use a key, check it and your API credit |
| The first message is very slow | Normal once: ThinkLess is being downloaded |

## Good to know

- **The counter** covers the prompts before the current one, and its amounts are API-equivalent: on a Claude plan you are not billed per token, so savings mean less of your plan's usage. The Opus figure is an estimate (the same tokens priced as Opus 5.5).
- **The cache** only reuses answers from the same project and the last 24 hours, when the new question is at least 85 % similar; the lead still checks that nothing it depends on (files, conversation) has changed. It saves the most on questions that would otherwise go to Sonnet or Opus.
- ThinkLess triages each message on its own, without the conversation, so a very short follow-up can be misjudged. Messages under three words and slash commands are never triaged.
- Details, measurements and limits: [README.md](README.md).
