"""The labelling request shape per model, checked without calling the API.

Opus 5.5 rejects a forced tool call with a 400, so it must get "auto"; Opus 5
keeps the forced call every validated Opus 5 label was made with.
"""

from types import SimpleNamespace as NS

from r3m.labeling import games, run
from r3m.labeling.schema import TOOL_NAME


class Recorder:
    def __init__(self):
        self.calls = []

    @property
    def messages(self):
        return self

    def create(self, **kw):
        self.calls.append(kw)
        tool = NS(type="tool_use", input={})  # fails validation: enough to stop after one call
        return NS(content=[tool], stop_reason="tool_use",
                  usage=NS(input_tokens=1, output_tokens=1,
                           cache_creation_input_tokens=0, cache_read_input_tokens=0))


def first_call(fn, model, **kw):
    rec = Recorder()
    try:
        fn(rec, model=model, effort="high", **kw)
    except Exception:
        pass
    return rec.calls[0]


def test_opus_5_5_gets_auto_and_opus_5_keeps_the_forced_call():
    for fn, kw in [(run._call, dict(champion_name="Ahri", title="t", role="mid", kit_text="k")),
                   (games._call, dict(name="Hades", mode=None))]:
        assert first_call(fn, "claude-opus-5-5", **kw)["tool_choice"] == {"type": "auto"}
        assert first_call(fn, "claude-opus-5", **kw)["tool_choice"] == {"type": "tool", "name": TOOL_NAME}


def test_no_thinking_field_and_effort_is_explicit():
    call = first_call(games._call, "claude-opus-5-5", name="Hades", mode=None)
    assert "thinking" not in call                         # 5.5 rejects disabled/enabled
    assert call["output_config"] == {"effort": "high"}    # 5.5 defaults to medium otherwise
    assert "temperature" not in call and "top_p" not in call


def test_opus_5_5_is_priced():
    u = run.Usage(calls=1, input=1_000_000, output=1_000_000, cache_write=1_000_000, cache_read=1_000_000)
    assert u.dollars("claude-opus-5-5") == 4.00 + 20.00 + 5.00 + 0.20


def test_the_win_condition_tool_is_byte_identical_to_the_validated_runs():
    # Generated from the schema.py that made label_run 9/10 (v3) and run 17
    # (games-v2); both produce this exact tool. A new model is only comparable
    # with the old labels if it is shown the same tool.
    import json
    from pathlib import Path
    from r3m.labeling.schema import tool_schema
    fixture = json.loads((Path(__file__).parent / "fixtures" / "tool_schema_win_condition.json").read_text())
    assert json.loads(json.dumps(tool_schema("macro_win_condition"), sort_keys=True)) == fixture


def test_the_v3_prompt_is_the_one_that_made_the_production_labels():
    # sha256 of prompt v3's system prompt as restored from git (0b8961e^).
    import hashlib
    from r3m.labeling import prompt_v3
    assert prompt_v3.PROMPT_VERSION == "v3"
    assert hashlib.sha256(prompt_v3.SYSTEM_PROMPT.encode()).hexdigest() == \
        "c49a6a91d015fe7b1db2b85530df557bac8ced3783adced81990c3f7013e4398"


def test_a_v3_run_sends_the_v3_prompt_and_the_win_condition_tool():
    call = first_call(run._call, "claude-opus-5-5", champion_name="Ahri", title="t", role="mid",
                      kit_text="k", prompt_version="v3")
    from r3m.labeling import prompt_v3
    assert call["system"][0]["text"] == prompt_v3.SYSTEM_PROMPT
    props = call["tools"][0]["input_schema"]["properties"]
    assert "macro_win_condition" in props and "macro_resources" not in props


def test_a_reply_without_the_tool_call_is_counted():
    class NoTool(Recorder):
        def create(self, **kw):
            self.calls.append(kw)
            return NS(content=[NS(type="text", text="Here are the scores...")], stop_reason="end_turn",
                      usage=NS(input_tokens=1, output_tokens=1,
                               cache_creation_input_tokens=0, cache_read_input_tokens=0))
    usage = run.Usage()
    try:
        games._call(NoTool(), model="claude-opus-5-5", effort="medium", name="Hades", mode=None, usage=usage)
    except RuntimeError:
        pass
    assert usage.calls == run.MAX_ATTEMPTS and usage.no_tool == run.MAX_ATTEMPTS and usage.invalid == 0
