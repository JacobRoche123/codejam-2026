import io
import json

import pytest
from conftest import FakeLLM, verdict

from thinkless import hook, llm
from thinkless.hook import format_advice, run, should_skip


@pytest.mark.parametrize("prompt", ["", "   ", "/mcp", "/exit now please", "thanks", "ok go"])
def test_short_prompts_and_slash_commands_are_skipped(prompt):
    assert should_skip(prompt)


def test_hook_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("THINKLESS_HOOK", "off")
    assert should_skip("Summarize this long report for me")


def test_skipped_prompt_costs_nothing():
    fake = FakeLLM([])
    assert run({"prompt": "thanks!"}, fake) == ""
    assert fake.calls == []


@pytest.mark.parametrize(
    ("complexity", "agent", "word"),
    [
        ("simple", "thinkless:small", "delegate"),
        ("medium", "thinkless:medium", "delegate"),
        ("complex", "thinkless:large", "most capable"),
    ],
)
def test_advice_names_the_right_subagent(complexity, agent, word):
    text = run({"prompt": "Please do this task for me"}, FakeLLM([verdict(complexity=complexity)]))
    assert text.startswith("[ThinkLess advice")
    assert f"\"{agent}\"" in text
    assert word in text


def test_ambiguous_prompt_asks_questions_first():
    fake = FakeLLM([verdict(clarity="ambiguous", questions=["Which language?"])])
    text = run({"prompt": "Write me a script please"}, fake)
    assert "ask the user these questions" in text
    assert "- Which language?" in text
    assert "subagent" not in text


def test_main_prints_advice_for_claude_code(monkeypatch, capsys):
    monkeypatch.setattr(hook, "AnthropicLLM", lambda: FakeLLM([verdict(complexity="medium")]))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"prompt": "Explain how HTTPS works"})))
    hook.main()
    assert "\"thinkless:medium\"" in capsys.readouterr().out


def test_main_never_blocks_the_prompt_on_errors(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exit_info:
        hook.main()
    assert exit_info.value.code == 1  # non-blocking for Claude Code (2 would block)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ThinkLess hook skipped" in captured.err


def test_api_key_lookup_order(monkeypatch, tmp_path):
    key_file = tmp_path / "api_key"
    monkeypatch.setattr(llm, "KEY_FILE", key_file)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("THINKLESS_ANTHROPIC_API_KEY", raising=False)
    assert llm.resolve_api_key() is None

    key_file.write_text("sk-from-file\n")
    assert llm.resolve_api_key() == "sk-from-file"

    monkeypatch.setenv("THINKLESS_ANTHROPIC_API_KEY", "sk-thinkless-var")
    assert llm.resolve_api_key() == "sk-thinkless-var"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-mcp-var")
    assert llm.resolve_api_key() == "sk-mcp-var"


def test_format_advice_shows_the_triage_cost():
    advice = {
        "status": "route",
        "reason": "short fact",
        "triage_cost": 0.0002,
        "recommendation": {"tier": "simple", "size": "small"},
        "brief": "",
    }
    assert "0.020 ¢" in format_advice(advice)
