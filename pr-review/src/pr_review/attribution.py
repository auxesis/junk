"""Model attribution: a footer on each comment and a collapsed record of the run."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from pr_review.payload import Comment, Payload, Source
from pr_review.plain_language.recommendation import recommend


@dataclass
class JobRecord:
    source: Source
    raw: int = 0
    error: str | None = None


@dataclass
class RunRecord:
    jobs: list[JobRecord] = field(default_factory=list)
    synthesis_model: str | None = None
    plain_language_model: str | None = None
    rewritten: int = 0
    reader_ran: bool = False
    needed_rewrite: int = 0
    stack_line: str | None = None
    context_line: str | None = None
    not_posted: list[str] = field(default_factory=list)


def _models(sources: list[Source]) -> list[tuple[str, str]]:
    return list(dict.fromkeys((s.agent, s.model) for s in sources))


def attribution(sources: list[Source]) -> str:
    models = _models(sources)
    if not models:
        return "<sub>Found by pr-review</sub>"
    per_agent = Counter(agent for agent, _ in models)
    names = [f"{a} ({m})" if per_agent[a] > 1 and m else a for a, m in models]
    noun = "model" if len(models) == 1 else "models"
    return f"<sub>Found by {len(models)} {noun}: {', '.join(names)}</sub>"


def render_details(record: RunRecord, comments: list) -> str:
    lines = [
        "<details>", "<summary>How this review was made</summary>", "",
        "| Agent | Model | Review type | Result |", "|---|---|---|---|",
    ]
    for job in record.jobs:
        s = job.source
        if job.error is not None:
            # The detail (which can name local paths) already went to stderr
            # from cli.main; the PR only needs to know the job failed.
            result = "failed"
        else:
            posted = sum(1 for c in comments if s in c.sources)
            result = f"{job.raw} found, {posted} posted"
        lines.append(f"| {s.agent} | {s.model or '(default)'} | {s.review_type} | {result} |")
    if record.synthesis_model:
        shared = sum(1 for c in comments if len(_models(c.sources)) > 1)
        lines += ["", (
            f"Synthesis: `{record.synthesis_model}` merged the findings, removed duplicates "
            f"and dropped findings it could not confirm in the code. {shared} posted "
            "finding(s) were raised by two or more models."
        )]
    if record.plain_language_model:
        if record.reader_ran:
            if record.needed_rewrite == 0:
                note = (f"Plain language: `{record.plain_language_model}` read every comment as a new "
                        "reader would. No comment had a problem that stopped the reader acting, "
                        "so none was rewritten.")
            else:
                note = (f"Plain language: `{record.plain_language_model}` read every comment as a new "
                        f"reader would. {record.needed_rewrite} comment(s) had a problem that stopped "
                        f"the reader acting; it rewrote {record.rewritten}.")
        else:
            note = (
                "Plain language: the reader test did not run; "
                "only the word-and-shape check was applied."
            )
        lines += ["", note]
    for line in (record.stack_line, record.context_line):
        if line:
            lines += ["", line]
    if record.not_posted:
        lines += ["", "**Findings not posted:**", ""] + [f"- {item}" for item in record.not_posted]
    lines += ["", "</details>"]
    return "\n".join(lines)


def finalize(payload: Payload, record: RunRecord) -> Payload:
    comments = [
        replace(c, body=f"{c.body.rstrip()}\n\n{attribution(c.sources)}")
        for c in payload.comments
    ]
    replies = [
        replace(r, body=f"{r.body.rstrip()}\n\n{attribution(r.sources)}")
        for r in payload.replies
    ]
    failed = sum(1 for j in record.jobs if j.error is not None)
    heading = recommend(payload, failed_jobs=failed, total_jobs=len(record.jobs))
    details = render_details(record, [*payload.comments, *payload.replies])
    body = f"{heading}\n\n{payload.body.rstrip()}\n\n{details}"
    return Payload(body=body, comments=comments, event=payload.event, replies=replies)
