import json

from conftest import FakeLLM, verdict

from thinkless import hook, memory


def write_transcript(path, lines):
    path.write_text("\n".join(json.dumps(line) for line in lines))
    return path


def human(text):
    return {"type": "user", "origin": {"kind": "human"}, "promptSource": "typed", "message": {"content": text}}


def answer(text, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}]}}


def test_last_exchange_takes_the_final_answer_of_the_last_answered_prompt(tmp_path):
    transcript = write_transcript(tmp_path / "t.jsonl", [
        human("What is the capital of Australia?"),
        answer("Let me think."),
        {"type": "user", "message": {"content": [{"type": "tool_result"}]}},   # not a human prompt
        answer("Subagent text", sidechain=True),                               # ignored
        answer("Canberra."),                                                    # final answer
        human("/clear"),                                                        # slash command: ignored
        human("A new prompt with no answer yet"),
    ])
    assert memory.last_exchange(transcript) == ("What is the capital of Australia?", "Canberra.")


def test_non_interactive_prompts_count_but_notifications_do_not(tmp_path):
    sdk_prompt = {"type": "user", "origin": None, "promptSource": "sdk", "message": {"content": "Capital of Peru?"}}
    notification = {"type": "user", "origin": {"kind": "task-notification"}, "promptSource": "system",
                    "message": {"content": "<task-notification>done</task-notification>"}}
    transcript = write_transcript(tmp_path / "t.jsonl", [sdk_prompt, answer("Lima."), notification])
    assert memory.last_exchange(transcript) == ("Capital of Peru?", "Lima.")


def test_last_exchange_handles_missing_or_broken_files(tmp_path):
    assert memory.last_exchange(tmp_path / "missing.jsonl") is None
    (tmp_path / "bad.jsonl").write_text("not json\n{}\n")
    assert memory.last_exchange(tmp_path / "bad.jsonl") is None


def test_remember_and_lookup_same_project_only():
    memory.remember("What is the capital of Australia?", "Canberra.", "/proj/a", now=1000)
    hit = memory.lookup("what is the capital of australia", "/proj/a", now=1100)
    assert hit is not None and hit[0]["answer"] == "Canberra." and hit[1] > 0.85
    assert memory.lookup("What is the capital of Australia?", "/proj/b", now=1100) is None


def test_lookup_needs_a_close_match():
    memory.remember("What is the capital of Australia?", "Canberra.", "/p", now=1000)
    assert memory.lookup("Write a poem about the sea", "/p", now=1100) is None


def test_entries_expire_after_a_day():
    memory.remember("What is the capital of Australia?", "Canberra.", "/p", now=1000)
    assert memory.lookup("What is the capital of Australia?", "/p", now=1000 + memory.TTL_SECONDS + 1) is None


def test_remember_replaces_the_same_question_and_caps_the_answer():
    memory.remember("Same question here", "old", "/p", now=1000)
    memory.remember("same  QUESTION here", "x" * 20000, "/p", now=1001)
    entries = memory.load(now=1002)
    assert len(entries) == 1
    assert len(entries[0]["answer"]) == memory.MAX_ANSWER_CHARS


def test_hook_offers_a_cached_answer_without_any_model_call(tmp_path):
    transcript = write_transcript(tmp_path / "t.jsonl", [
        human("What is the capital of Australia?"), answer("Canberra."),
    ])
    fake = FakeLLM([])
    text = hook.run({"prompt": "What is the capital of Australia?", "transcript_path": str(transcript),
                     "cwd": "/p"}, fake)
    assert text.startswith("[ThinkLess cache")
    assert "Canberra." in text
    assert fake.calls == []  # no triage call: the cache is free


def test_stop_event_stores_the_exchange_and_prints_nothing(tmp_path, monkeypatch, capsys):
    import io

    transcript = write_transcript(tmp_path / "t.jsonl", [human("What is the capital of Peru?"), answer("Lima.")])
    event = {"hook_event_name": "Stop", "transcript_path": str(transcript), "cwd": "/p"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    hook.main()
    assert capsys.readouterr().out == ""
    hit = memory.lookup("What is the capital of Peru?", "/p")
    assert hit and hit[0]["answer"] == "Lima."


def test_without_a_key_the_hook_adds_nothing_and_the_router_triages():
    # isolated_files removed every key, and no llm is injected
    assert hook.run({"prompt": "Write a Python function to sort a list", "cwd": "/p"}) == ""


def test_with_a_key_the_hook_names_the_model(monkeypatch):
    monkeypatch.setattr(hook, "resolve_api_key", lambda: "sk-test")
    monkeypatch.setattr(hook, "AnthropicLLM", lambda: FakeLLM([verdict(complexity="complex")]))
    text = hook.run({"prompt": "Design a ride-sharing system", "cwd": "/p"})
    assert "Model: Claude Opus 5.5" in text
