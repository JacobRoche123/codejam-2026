# ThinkLess

**Ask before thinking. Then use the smallest Claude model that does the job.**

ThinkLess is a plugin for Claude Code that acts as a conductor. Before Claude works on your request, ThinkLess reads it for a fraction of a cent and decides which Claude model it really needs: **Claude Haiku 5.5** for simple questions, **Claude Sonnet 5.5** for everyday code and explanations, **Claude Opus 5.5** for hard reasoning and system design, and, rarely, **Claude Fable 5.2** for research-level work. A fast Haiku lead answers the simple requests itself and hands everything else to the model ThinkLess named, so you stop paying top-model prices for easy work. On our 20-task benchmark this cut the API bill by **60 %** and used **27 % fewer tokens** than sending everything to Opus, while keeping **91 % of its quality** (graded blind). Fewer tokens on smaller models also means less computation on GPUs, so less electricity and fewer emissions behind each answer. We do not convert that into watt-hours, because Anthropic does not publish energy figures per request.

| Your request looks like… | ThinkLess picks |
|---|---|
| A fact, a translation, a short rewrite | Claude Haiku 5.5 · effort low |
| Code, a multi-step explanation, a summary, a plan | Claude Sonnet 5.5 · effort medium |
| Hard reasoning, a proof, system design with trade-offs | Claude Opus 5.5 · effort high |
| Research-level work (rare) | Claude Fable 5.2 · effort high |
| Something vague | Up to 3 short questions first |

---

## Install in Claude Code (Mac, about 10 minutes)

You need a Claude plan that includes Claude Code, and an Anthropic API key (ThinkLess's triage costs about 0.02 cents per message, billed to that key).

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

### 4. Give ThinkLess its API key

Create a key at [console.anthropic.com](https://console.anthropic.com/) (Settings → API Keys, add a little credit under Billing) and copy it. Then run this and paste the key when asked. Nothing appears while you paste: that is normal.

```bash
mkdir -p ~/.config/thinkless && read -s "K?Paste your Anthropic API key: " && printf '%s' "$K" > ~/.config/thinkless/api_key && chmod 600 ~/.config/thinkless/api_key && unset K && echo "Key saved"
```

You should see `Key saved`. The key stays in a private file on your Mac. Do not export it as `ANTHROPIC_API_KEY` in your shell: Claude Code would then bill your API key instead of your Claude plan.

### 5. Install the plugin

```bash
claude plugin marketplace add JacobRoche123/codejam-2026
```

```bash
claude plugin install thinkless@thinkless
```

You should see two success messages. Check with `claude plugin list`: **thinkless** is listed and enabled.

### 6. Start Claude Code with the ThinkLess conductor

```bash
claude --agent thinkless:router
```

The header shows **Haiku 5.5** and **@thinkless:router**. The first message can take a few extra seconds while ThinkLess downloads.

### 7. Use Claude as usual

Try these three requests and watch who does the work:

| Type this | You should see |
|---|---|
| `What is the capital of Australia?` | An instant answer from the Haiku lead, no subagent |
| `Write a Python function that reads a CSV of expenses and returns the total per category, skipping invalid lines` | A **thinkless:sonnet** block: Claude Sonnet 5.5 writes the code |
| `Design the architecture of a ride-sharing app for 50,000 students, with the main trade-offs` | A **thinkless:opus** block: Claude Opus 5.5 works for about a minute, then the full design appears |

To see ThinkLess's advice for a message, press **Ctrl + O** after the answer.

---

## Everyday commands

| To… | Run |
|---|---|
| Update ThinkLess | `claude plugin marketplace update thinkless` then `claude plugin update thinkless@thinkless` |
| Skip ThinkLess for one session | `THINKLESS_HOOK=off claude` |
| Turn it off everywhere | `claude plugin disable thinkless@thinkless` |
| Uninstall | `claude plugin uninstall thinkless@thinkless` |

## If something goes wrong

| You see | Do this |
|---|---|
| `command not found: claude` or `uvx` | Quit and reopen the Terminal; if it persists, redo step 2 or 3 |
| No **thinkless:sonnet** or **thinkless:opus** block | Check that the header says **@thinkless:router**; restart with `claude --agent thinkless:router` |
| "ThinkLess hook skipped" or "needs an Anthropic API key" | Redo step 4, and check your API credit on console.anthropic.com |
| The first message is very slow | Normal once: ThinkLess is being downloaded |

## Good to know

- ThinkLess triages each message on its own, without the conversation, so a very short follow-up can be misjudged.
- Messages under three words and slash commands are never triaged.
- Want to see what ThinkLess saved on a given prompt, and at what quality? The demo app's **Savings report** compares it with Claude Opus 5.5 and a blind judge. Details, measurements and limits: [README.md](README.md).
