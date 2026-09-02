"""The shared agent runner: fd isolation, output relay, payload-over-status."""
import fcntl
import io
import json
import os
import sys

import pytest

from pr_review.payload import Payload
from pr_review.reviewers._run import run_agent, run_cli_payload

VALID = json.dumps({"body": "review body", "comments": []})


def fake_runner(*, writes=VALID, status=0, seen=None):
    """A runner that writes `writes` to the payload path named in the prompt."""
    def run(cmd, prompt, *, workdir, sink=None):
        path = prompt.strip().splitlines()[-1]
        if seen is not None:
            seen.update(cmd=list(cmd), prompt=prompt, workdir=workdir, path=path)
        if writes is not None:
            with open(path, "w", encoding="utf-8") as f:
                f.write(writes)
        return status
    return run


def build(path):
    return f"review the PR and write:\n{path}"


def run(**kwargs):
    return run_cli_payload(["agent"], build, workdir="/tmp", runner=fake_runner(**kwargs))


# --- run_cli_payload: the payload file is the contract, not the exit status ---

def test_returns_the_payload_the_agent_wrote():
    payload = run()
    assert isinstance(payload, Payload)
    assert payload.body == "review body"


def test_a_complete_payload_survives_a_nonzero_exit_status():
    """`codex` has finished a review, written a valid payload, then died on the way
    out (EAGAIN panic, exit 101). That must not cost the whole job."""
    assert run(status=101).body == "review body"


def test_an_empty_payload_reports_the_exit_status():
    with pytest.raises(RuntimeError, match="empty payload.*exit status 101"):
        run(writes="   ", status=101)


def test_a_missing_payload_file_reports_the_exit_status():
    with pytest.raises(RuntimeError, match="empty payload.*exit status 2"):
        run(writes=None, status=2)


def test_a_malformed_payload_reports_the_exit_status():
    with pytest.raises(ValueError, match="exit status 101"):
        run(writes="not json", status=101)


def test_the_prompt_names_a_real_temp_path_that_is_cleaned_up():
    seen = {}
    run_cli_payload(["agent"], build, workdir="/w", runner=fake_runner(seen=seen))
    assert seen["cmd"] == ["agent"]
    assert seen["workdir"] == "/w"
    assert os.path.basename(seen["path"]).startswith("pr-review-payload.")
    assert not os.path.exists(seen["path"])


def test_the_payload_file_is_cleaned_up_after_a_failure():
    seen = {}
    with pytest.raises(RuntimeError):
        run_cli_payload(
            ["agent"], build, workdir="/w",
            runner=fake_runner(writes="", status=1, seen=seen),
        )
    assert not os.path.exists(seen["path"])


# --- run_agent: the agent runs on pipes of ours, never our own stdio ---

def child(code):
    return [sys.executable, "-c", code]


def nonblock(fd):
    return bool(fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_NONBLOCK)


def test_an_agent_cannot_set_o_nonblock_on_our_stdio(tmp_path):
    """The bug: `claude` sets O_NONBLOCK on the stdio it inherits, and the flag lives
    on the shared open file description — so a sibling `codex` write hits EAGAIN and
    Rust panics. Private pipes mean a child's flags stay the child's."""
    before = [nonblock(f.fileno()) for f in (sys.__stdout__, sys.__stderr__)]
    status = run_agent(
        child(
            "import fcntl, os, sys\n"
            "for fd in (1, 2):\n"
            "    fcntl.fcntl(fd, fcntl.F_SETFL,"
            " fcntl.fcntl(fd, fcntl.F_GETFL) | os.O_NONBLOCK)\n"
        ),
        "", workdir=str(tmp_path), sink=io.StringIO(),
    )
    assert status == 0
    assert [nonblock(f.fileno()) for f in (sys.__stdout__, sys.__stderr__)] == before


def test_the_agent_reads_the_prompt_on_stdin(tmp_path):
    sink = io.StringIO()
    run_agent(
        child("import sys; sys.stdout.write(sys.stdin.read().upper())"),
        "review this", workdir=str(tmp_path), sink=sink,
    )
    assert sink.getvalue() == "REVIEW THIS"


def test_both_agent_streams_are_relayed_to_the_sink(tmp_path):
    sink = io.StringIO()
    run_agent(
        child("import sys; print('out'); sys.stderr.write('err\\n')"),
        "", workdir=str(tmp_path), sink=sink,
    )
    assert sorted(sink.getvalue().split()) == ["err", "out"]


def test_the_agent_exit_status_is_returned(tmp_path):
    assert run_agent(
        child("raise SystemExit(101)"), "", workdir=str(tmp_path), sink=io.StringIO()
    ) == 101


def test_an_agent_that_never_reads_its_prompt_does_not_raise(tmp_path):
    """A crash-on-startup agent closes stdin under the feeder thread; that
    BrokenPipeError must surface as an exit status, not an exception."""
    assert run_agent(
        child("raise SystemExit(2)"), "x" * 500_000,
        workdir=str(tmp_path), sink=io.StringIO(),
    ) == 2


def test_the_agent_runs_in_the_workdir_with_mise_trust(tmp_path, monkeypatch):
    monkeypatch.delenv("MISE_TRUSTED_CONFIG_PATHS", raising=False)
    sink = io.StringIO()
    run_agent(
        child("import os; print(os.getcwd()); print(os.environ['MISE_TRUSTED_CONFIG_PATHS'])"),
        "", workdir=str(tmp_path), sink=sink,
    )
    cwd, trusted = sink.getvalue().splitlines()
    assert os.path.realpath(cwd) == os.path.realpath(tmp_path)
    assert trusted == str(tmp_path)
