import builtins
import io
import sys

from pr_review import terminal


def _no_dev_tty(monkeypatch):
    """Make open('/dev/tty') fail, mimicking a process with no controlling tty."""
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if path == "/dev/tty":
            raise OSError("no controlling terminal")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)


def _fake_stdin(monkeypatch, *, isatty: bool, data: str = ""):
    fake = io.StringIO(data)
    fake.isatty = lambda: isatty
    monkeypatch.setattr(sys, "stdin", fake)
    return fake


def test_can_prompt_true_when_stdin_is_tty(monkeypatch):
    _fake_stdin(monkeypatch, isatty=True)
    assert terminal.can_prompt() is True


def test_can_prompt_false_without_any_terminal(monkeypatch):
    _no_dev_tty(monkeypatch)
    _fake_stdin(monkeypatch, isatty=False)
    assert terminal.can_prompt() is False


def test_open_interactive_falls_back_to_stdin(monkeypatch):
    # /dev/tty unopenable (e.g. screen / detached session) but stdin is a real tty.
    _no_dev_tty(monkeypatch)
    _fake_stdin(monkeypatch, isatty=True, data="claude\n")
    result = terminal.open_interactive()
    assert result is not None
    read_line, write, close = result
    assert read_line() == "claude\n"
    write("noop")  # writes to stderr; must not raise
    close()


def test_open_interactive_none_without_terminal(monkeypatch):
    _no_dev_tty(monkeypatch)
    _fake_stdin(monkeypatch, isatty=False)
    assert terminal.open_interactive() is None
