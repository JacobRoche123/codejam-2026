import json

import pytest

from thinkless import savings


def usage(inp=0, out=0, read=0, w1h=0):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
            "cache_creation_input_tokens": w1h,
            "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": w1h}}


def assistant(model, req, u, content=None, sidechain=False):
    return {"type": "assistant", "requestId": req, "isSidechain": sidechain, "timestamp": "2026-11-21T20:00:00Z",
            "message": {"model": model, "usage": u, "content": content or [{"type": "text", "text": "ok"}]}}


def human(text):
    return {"type": "user", "origin": {"kind": "human"}, "promptSource": "typed",
            "cwd": "/Users/me/proj", "timestamp": "2026-11-21T20:00:00Z", "message": {"content": text}}


def write(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries))


def test_usage_cost_uses_published_prices_and_the_1h_cache_write_rate():
    # Opus 5.5: $4 in, $20 out, cache read $0.20, 1-hour cache write = 2 × $4
    assert savings.usage_cost("claude-opus-5-5", usage(inp=1_000_000)) == pytest.approx(4.0)
    assert savings.usage_cost("claude-opus-5-5", usage(out=1_000_000)) == pytest.approx(20.0)
    assert savings.usage_cost("claude-opus-5-5", usage(read=1_000_000)) == pytest.approx(0.20)
    assert savings.usage_cost("claude-opus-5-5", usage(w1h=1_000_000)) == pytest.approx(8.0)
    # The same Haiku usage priced as Opus
    assert savings.usage_cost("claude-haiku-5-5", usage(out=1_000_000), price_as="claude-opus-5-5") == pytest.approx(20.0)


@pytest.fixture
def project(tmp_path):
    """A fake ~/.claude/projects with one ThinkLess Router session."""
    session = tmp_path / "projects" / "-Users-me-proj" / "s1.jsonl"
    write(session, [
        {"type": "agent-setting", "agentSetting": "thinkless:router"},
        # Turn 1: delegated to the Sonnet worker. The lead's response is logged on two lines
        # (thinking + tool call) that repeat the same usage: it must be counted once.
        human("Write a CSV parser"),
        {"type": "attachment", "attachment": {"type": "hook_success",
         "content": "[ThinkLess advice · triage by Claude Haiku · cost 0.020 ¢]\nModel: Claude Sonnet 5.5"}},
        assistant("claude-haiku-5-5", "r1", usage(out=1000), [{"type": "thinking", "thinking": ""}]),
        assistant("claude-haiku-5-5", "r1", usage(out=1000), [{"type": "tool_use", "id": "tool-1", "name": "Agent"}]),
        # Turn 2: simple, answered by the lead itself.
        human("Capital of Australia?"),
        assistant("claude-haiku-5-5", "r2", usage(out=100)),
    ])
    sub = session.parent / "s1" / "subagents"
    write(sub / "agent-x.jsonl", [assistant("claude-sonnet-5-5", "r9", usage(out=10_000), sidechain=True)])
    (sub / "agent-x.meta.json").write_text(json.dumps({"agentType": "thinkless:sonnet", "toolUseId": "tool-1"}))
    return tmp_path / "projects"


def test_turns_attribute_lead_worker_and_triage_costs(project):
    turns = {t.prompt: t for t in savings.collect(project, days=None)}
    delegated = turns["Write a CSV parser"]
    assert len(delegated.lead) == 1                      # deduplicated by requestId
    assert delegated.workers[0][2] == "thinkless:sonnet"
    assert delegated.triage_cost == pytest.approx(0.0002)
    # Actual: Haiku 1000 out ($0.0005) + Sonnet 10,000 out ($0.10) + triage ($0.0002)
    assert delegated.actual == pytest.approx(0.0005 + 0.10 + 0.0002)
    # Opus estimate: the worker's 10,000 output tokens at $20 per million
    assert delegated.opus_estimate == pytest.approx(0.20)

    simple = turns["Capital of Australia?"]
    assert simple.workers == []
    assert simple.opus_estimate == pytest.approx(100 * 20 / 1_000_000)


def test_sessions_that_ignore_thinkless_are_not_counted(tmp_path):
    # A plain Opus session that received advice but did all the work itself.
    write(tmp_path / "p" / "-x" / "s.jsonl", [
        human("Do something big"),
        {"type": "attachment", "attachment": {"content": "[ThinkLess advice · triage by Claude Haiku · cost 0.020 ¢]"}},
        assistant("claude-opus-5-5", "r1", usage(out=5000)),
    ])
    assert savings.collect(tmp_path / "p", days=None) == []


def test_summary_and_report(project):
    turns = savings.collect(project, days=None)
    summary = savings.summarize(turns)
    assert summary["prompts"] == 2
    assert summary["saved"] > 0 and 0 < summary["saved_pct"] < 100
    page = savings.render_html(turns, summary, days=30)
    assert "ThinkLess savings" in page and "Write a CSV parser" in page and "no API call made" in page


def test_local_time_converts_utc():
    assert savings.local_time("bad") == "bad"
    assert len(savings.local_time("2026-11-21T20:00:00Z")) == 16


def test_running_total_matches_the_full_scan_and_reuses_its_index(project, tmp_path):
    index = tmp_path / "index.json"
    total = savings.running_total(project, days=36500, index_file=index)
    summary = savings.summarize(savings.collect(project, days=None))
    assert total["prompts"] == summary["prompts"] == 2
    assert total["saved"] == pytest.approx(summary["saved"])
    # Second call: unchanged files are not parsed again.
    calls = []
    original = savings.read_session
    savings.read_session = lambda p: calls.append(p) or original(p)
    try:
        assert savings.running_total(project, days=36500, index_file=index)["prompts"] == 2
    finally:
        savings.read_session = original
    assert calls == []


def test_counter_text():
    assert "nothing yet" in savings.counter_text({"prompts": 0, "actual": 0, "opus": 0, "saved": 0})
    text = savings.counter_text({"prompts": 23, "actual": 2.0, "opus": 3.2, "saved": 1.2})
    assert text == "saved so far: $1.20 vs Opus 5.5 (−38 %) over 23 prompts"
