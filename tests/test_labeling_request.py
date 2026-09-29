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
