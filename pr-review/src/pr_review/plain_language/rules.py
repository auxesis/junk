"""Load rules.json and render the writing rules every prompt receives."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cache
from importlib.resources import files


@dataclass(frozen=True)
class BlockingWord:
    word: str
    pattern: re.Pattern[str]
    instead: str


@dataclass(frozen=True)
class Rules:
    sentence_minor_words: int
    sentence_blocking_words: int
    labels: dict[str, str]
    required_labels: tuple[str, ...]
    urgency: dict[str, str]
    recommendation: dict[str, tuple[str, str]]
    blocking_words: tuple[BlockingWord, ...]


@cache
def load_rules() -> Rules:
    data = json.loads(files(__package__).joinpath("rules.json").read_text(encoding="utf-8"))
    return Rules(
        sentence_minor_words=data["sentence_minor_words"],
        sentence_blocking_words=data["sentence_blocking_words"],
        labels=dict(data["labels"]),
        required_labels=tuple(data["required_labels"]),
        urgency=dict(data["urgency"]),
        recommendation={k: (v["emoji"], v["text"]) for k, v in data["recommendation"].items()},
        blocking_words=tuple(
            BlockingWord(w["word"], re.compile(w["pattern"], re.IGNORECASE), w["instead"])
            for w in data["blocking_words"]
        ),
    )


@cache
def writing_rules_block() -> str:
    r = load_rules()
    impact, evidence, fix = r.labels["impact"], r.labels["evidence"], r.labels["fix"]
    urgency = "\n".join(f'  - {level}: "{phrase}:"' for level, phrase in r.urgency.items())
    words = "\n".join(f'- "{w.word}": {w.instead}' for w in r.blocking_words)
    red, yellow, green = (r.recommendation[k][1] for k in ("red", "yellow", "green"))
    block_phrase, change_phrase = r.urgency["block"], r.urgency["request-changes"]
    return f"""## How to write each comment (REQUIRED)

Write every comment, and the review body, for this reader: an engineer on the
team who did not write this code, does not know this part of the system, and may
not have English as a first language. They must be able to act on each comment
without asking anyone.

Every inline comment has this shape, in this order:

    **<finding line: one sentence that says what is wrong>**

    **{impact}:** <what breaks, and when>

    **{evidence}:** <optional: how you know, such as a file and line or a command and its output>

    **{fix}:** <what to change; any code goes here, and only here>

- The finding line is bold and comes first. Do not add a "Problem:" label.
- If your instructions have a severity ladder, start the finding line with the
  plain phrase for the level, never with the ladder's own name:
{urgency}
- {impact} and {fix} are required. Leave out {evidence} only when the finding
  line already shows how you know.

Writing rules (from ISO 24495-1 plain language and ASD-STE100 Simplified
Technical English):

1. Put the most important information first. (ISO 24495-1)
2. Keep one idea in each sentence. (ISO 24495-1)
3. Keep most sentences under 20 words. Split a sentence over
   {r.sentence_minor_words} words unless it is a list of paths or a quoted
   message. Never write a sentence over {r.sentence_blocking_words} words.
   (ASD-STE100, Sentences)
4. Use the active voice. Say who or what does the action. (ASD-STE100, Verbs)
5. Write negatives in full: "does not" and "cannot", never "doesn't" or "can't".
   (ISO 24495-1)
6. Use literal words, with no metaphor and no programmer slang. Say what
   happens: "the alert does not fire", not "the guard is inert". (ISO 24495-1)
7. Use one term for one thing. Keep the repository's own words. If the diff shows
   what a repository term means, define it once, in a few words. Never replace a
   term with a similar general word. (ASD-STE100, Words)
8. Keep exact technical names: identifiers, commands, file paths, product names
   and real engineering terms. Put code names in backticks.
9. Use code fences only for code, commands and command output. Never put an
   explanation inside a fence.
10. Each comment must make sense alone. Do not refer to "the above", another
    comment, or a term only defined elsewhere.

Never use these words and phrases; write the plain words instead:
{words}

pr-review adds a Recommendation heading above the review body. It is
"{red}" if any finding starts with "{block_phrase}:"; otherwise "{yellow}" if
any finding starts with "{change_phrase}:" or has no urgency phrase; otherwise
"{green}". Do not write your own recommendation heading. Start the body with
one or two sentences that say what must change before merging, if anything,
and what can wait.
"""
