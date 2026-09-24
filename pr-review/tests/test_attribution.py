from pr_review.attribution import JobRecord, RunRecord, attribution, finalize, render_details
from pr_review.payload import Comment, Payload, Source

OPUS = Source("claude", "claude-opus-5", "test-gap")
OPUS_INFRA = Source("claude", "claude-opus-5", "infracode")
SONNET = Source("claude", "claude-sonnet-5", "test-gap")
CODEX = Source("codex", "gpt-5.6-terra", "test-gap")


def test_one_source():
    assert attribution([OPUS]) == "<sub>Found by 1 model: claude</sub>"


def test_two_agents_list_agent_names_only():
    assert attribution([OPUS, CODEX]) == "<sub>Found by 2 models: claude, codex</sub>"


def test_one_agent_with_two_models_names_the_models():
    assert attribution([OPUS, SONNET]) == (
        "<sub>Found by 2 models: claude (claude-opus-5), claude (claude-sonnet-5)</sub>"
    )


def test_two_review_types_on_one_model_count_as_one_model():
    assert attribution([OPUS, OPUS_INFRA]) == "<sub>Found by 1 model: claude</sub>"


def test_no_known_source():
    assert attribution([]) == "<sub>Found by pr-review</sub>"


def test_details_list_every_job_with_found_and_posted_counts():
    record = RunRecord(jobs=[JobRecord(OPUS, raw=3), JobRecord(CODEX, error="boom\ntrace")])
    comments = [Comment("a", 1, "x", sources=[OPUS]), Comment("b", 2, "y", sources=[OPUS, CODEX])]
    text = render_details(record, comments)
    assert text.startswith("<details>\n<summary>How this review was made</summary>")
    assert "| claude | claude-opus-5 | test-gap | 3 found, 2 posted |" in text
    assert "| codex | gpt-5.6-terra | test-gap | failed: boom |" in text
    assert text.rstrip().endswith("</details>")
    assert "Synthesis" not in text and "Plain language" not in text


def test_details_mention_synthesis_and_plain_language_when_they_ran():
    record = RunRecord(jobs=[JobRecord(OPUS, raw=1), JobRecord(CODEX, raw=1)],
                       synthesis_model="claude-opus-5", plain_language_model="claude-opus-5", rewritten=2)
    comments = [Comment("b", 2, "y", sources=[OPUS, CODEX])]
    text = render_details(record, comments)
    assert "Synthesis: `claude-opus-5`" in text
    assert "1 posted finding(s) were raised by two or more models." in text
    assert "Plain language: `claude-opus-5`" in text and "rewrote 2" in text


def test_a_pipe_in_an_error_does_not_break_the_table():
    text = render_details(RunRecord(jobs=[JobRecord(CODEX, error="a | b")]), [])
    assert "failed: a \\| b" in text


def test_finalize_appends_footers_and_details_without_changing_the_input():
    p = Payload(body="Verdict.", comments=[Comment("a", 1, "**X.**", sources=[OPUS, CODEX])])
    out = finalize(p, RunRecord(jobs=[JobRecord(OPUS, raw=1), JobRecord(CODEX, raw=1)]))
    assert out.comments[0].body == "**X.**\n\n<sub>Found by 2 models: claude, codex</sub>"
    assert out.body.startswith("Verdict.\n\n<details>")
    assert p.comments[0].body == "**X.**"
    assert (out.comments[0].path, out.comments[0].line) == ("a", 1)
