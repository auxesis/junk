from types import SimpleNamespace

import pytest

from pr_review.coop import (
    CoopExecutor,
    CoopUnavailable,
    HostExecutor,
    create_vm,
    destroy_vm,
    install_ssh_alias,
    preflight,
    vm_name,
    vm_size,
)


def test_vm_size_scales_with_jobs_within_caps():
    assert vm_size(1) == (2, 4096)  # floors apply
    assert vm_size(3) == (3, 4608)  # 3 vcpus, 3*1536 mem
    assert vm_size(20) == (8, 12288)  # ceilings apply


def test_vm_size_treats_zero_jobs_as_the_floor():
    assert vm_size(0) == (2, 4096)


def test_vm_name_sanitises_and_suffixes():
    name = vm_name("My.Org", "repo/sub", 42, suffix="ab12")
    assert name == "pr-review-my-org-repo-sub-42-ab12"
    assert all(c.isalnum() or c == "-" for c in name)


def test_vm_name_default_suffix_is_four_hex_chars():
    name = vm_name("o", "r", 1)
    suffix = name.rsplit("-", 1)[1]
    assert len(suffix) == 4
    int(suffix, 16)


def _runner(version=0, images="default\n", proxy="anthropic: on\n"):
    def runner(cmd, **kw):
        if cmd[:2] == ["coop", "proxy"]:
            return SimpleNamespace(returncode=0, stdout=proxy)
        if cmd[:2] == ["coop", "images"]:
            return SimpleNamespace(returncode=0, stdout=images)
        return SimpleNamespace(returncode=version, stdout="coop 1\n")

    return runner


def test_preflight_passes_when_everything_is_present():
    preflight(runner=_runner())


def test_preflight_raises_when_proxy_missing_and_names_the_fix():
    with pytest.raises(CoopUnavailable) as e:
        preflight(runner=_runner(proxy="anthropic: off\n"))
    assert "claude setup-token" in str(e.value)
    assert "coop proxy setup" in str(e.value)


def test_preflight_raises_when_binary_missing():
    def runner(cmd, **kw):
        raise FileNotFoundError("coop")

    with pytest.raises(CoopUnavailable) as e:
        preflight(runner=runner)
    assert "coop setup" in str(e.value)


def test_preflight_raises_when_binary_exits_nonzero():
    with pytest.raises(CoopUnavailable, match="coop setup"):
        preflight(runner=_runner(version=1))


def test_preflight_raises_when_no_template():
    with pytest.raises(CoopUnavailable, match="coop setup"):
        preflight(runner=_runner(images="  \n"))


def test_preflight_raises_when_proxy_status_fails():
    def runner(cmd, **kw):
        if cmd[:2] == ["coop", "proxy"]:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(returncode=0, stdout="default\n")

    with pytest.raises(CoopUnavailable, match="coop proxy setup"):
        preflight(runner=runner)


def _recording(returncode=0):
    seen = []

    def runner(cmd, **kw):
        seen.append(cmd)
        return SimpleNamespace(returncode=returncode, stdout="")

    return seen, runner


def test_create_vm_builds_the_right_argv():
    seen, runner = _recording()
    create_vm("/clone", "pr-review-o-r-1-ab12", vcpus=3, mem=4608, runner=runner)
    cmd = seen[0]
    assert cmd[:2] == ["coop", "up"]
    assert "/clone" in cmd
    assert "--name" in cmd and "pr-review-o-r-1-ab12" in cmd
    assert "--new-instance" in cmd and "--no-prompt" in cmd
    assert "--vcpus" in cmd and "3" in cmd
    assert "--mem" in cmd and "4608" in cmd
    assert "--exclude-git" not in cmd
    assert "--no-agents" not in cmd


def test_create_vm_raises_on_nonzero_exit():
    _, runner = _recording(returncode=1)
    with pytest.raises(CoopUnavailable):
        create_vm("/clone", "n", vcpus=2, mem=4096, runner=runner)


def test_install_ssh_alias_runs_ssh_config():
    seen, runner = _recording()
    install_ssh_alias("vm1", runner=runner)
    assert seen[0] == ["coop", "ssh-config", "vm1"]


def test_destroy_vm_runs_destroy():
    seen, runner = _recording()
    destroy_vm("vm1", runner=runner)
    assert seen[0] == ["coop", "destroy", "vm1"]


def test_destroy_vm_never_raises():
    _, runner = _recording(returncode=1)
    destroy_vm("vm1", runner=runner)

    def boom(cmd, **kw):
        raise FileNotFoundError("coop")

    destroy_vm("vm1", runner=boom)


def test_create_vm_error_includes_coop_stderr():
    def runner(cmd, **kw):
        return SimpleNamespace(returncode=2, stdout="", stderr="no free port\n")

    with pytest.raises(CoopUnavailable, match="no free port"):
        create_vm("/clone", "n", vcpus=2, mem=4096, runner=runner)


def test_install_ssh_alias_raises_on_nonzero_exit_with_stderr():
    def runner(cmd, **kw):
        return SimpleNamespace(returncode=1, stdout="", stderr="unknown vm")

    with pytest.raises(CoopUnavailable, match="unknown vm"):
        install_ssh_alias("vm1", runner=runner)


def test_create_vm_and_install_ssh_alias_wrap_oserror():
    def runner(cmd, **kw):
        raise FileNotFoundError("coop")

    with pytest.raises(CoopUnavailable, match="coop setup"):
        create_vm("/clone", "n", vcpus=2, mem=4096, runner=runner)
    with pytest.raises(CoopUnavailable, match="coop setup"):
        install_ssh_alias("vm1", runner=runner)


def test_coop_executor_runs_over_ssh_and_reads_the_guest_payload():
    import json
    from pr_review.coop import CoopExecutor

    calls = []

    def agent_runner(cmd, prompt, *, workdir):
        calls.append(("agent", cmd, prompt, workdir))
        return 0

    def cat_runner(name, path):
        calls.append(("cat", name, path))
        return json.dumps({"body": "b", "comments": []})

    ex = CoopExecutor("pr-review-o-r-1-ab12", host_workdir="/host",
                      agent_runner=agent_runner, cat_runner=cat_runner)
    out = ex.run_json(["claude", "--print"], lambda p: f"PROMPT->{p}", workdir="/ignored")
    assert out == {"body": "b", "comments": []}
    agent_cmd = calls[0][1]
    assert agent_cmd[0] == "ssh" and "coop-pr-review-o-r-1-ab12" in agent_cmd
    guest_payload = [c for c in calls if c[0] == "cat"][0][2]
    assert guest_payload.startswith("/workspace/.git/pr-review/")
    assert "MISE_TRUSTED_CONFIG_PATHS=/workspace" in " ".join(agent_cmd)
    assert "/workspace" in " ".join(agent_cmd)
    assert calls[0][2] == f"PROMPT->{guest_payload}"


def test_coop_executor_reports_an_empty_payload():
    import pytest
    from pr_review.coop import CoopExecutor

    ex = CoopExecutor("vm", host_workdir="/host", agent_runner=lambda *a, **k: 0,
                      cat_runner=lambda name, path: "")
    with pytest.raises(RuntimeError, match="empty payload"):
        ex.run_json(["claude"], lambda p: p, workdir="/x")


def test_host_executor_delegates_to_run_cli_json(monkeypatch):
    from pr_review import coop

    seen = {}

    def fake(command, build_prompt, *, workdir, parse):
        seen.update(command=command, workdir=workdir, parse=parse)
        return "ok"

    monkeypatch.setattr(coop, "run_cli_json", fake)
    assert coop.HostExecutor().run_json(["x"], lambda p: p, workdir="/w") == "ok"
    assert seen["command"] == ["x"] and seen["workdir"] == "/w"


def test_coop_executor_remote_command_creates_dir_before_cd():
    from pr_review.coop import CoopExecutor

    seen = []
    ex = CoopExecutor("vm", host_workdir="/host",
        agent_runner=lambda cmd, prompt, *, workdir: seen.append(cmd) or 0,
        cat_runner=lambda name, path: "{}",
    )
    ex.run_json(["claude", "--print", "a b"], lambda p: p, workdir="/x")
    assert seen[0][:2] == ["ssh", "coop-vm"]
    assert seen[0][2] == (
        "mkdir -p /workspace/.git/pr-review && cd /workspace && "
        "MISE_TRUSTED_CONFIG_PATHS=/workspace claude --print 'a b'"
    )


def test_coop_executor_payload_wins_over_nonzero_status():
    from pr_review.coop import CoopExecutor

    ex = CoopExecutor("vm", host_workdir="/host", agent_runner=lambda *a, **k: 101,
                      cat_runner=lambda name, path: '{"ok": true}')
    assert ex.run_json(["codex"], lambda p: p, workdir="/x") == {"ok": True}


def test_coop_executor_applies_custom_parse():
    from pr_review.coop import CoopExecutor

    ex = CoopExecutor("vm", host_workdir="/host", agent_runner=lambda *a, **k: 0,
                      cat_runner=lambda name, path: "  raw text \n")
    assert ex.run_json(["x"], lambda p: p, workdir="/x", parse=str.strip) == "raw text"


def test_ssh_cat_raises_with_stderr_on_failure(monkeypatch):
    import subprocess
    import pytest
    from pr_review import coop

    monkeypatch.setattr(
        coop.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 255, "", "connection refused\n"),
    )
    with pytest.raises(RuntimeError, match="exit status 255: connection refused"):
        coop._ssh_cat("vm", "/workspace/p.json")


def test_ssh_cat_returns_stdout_on_success(monkeypatch):
    import subprocess
    from pr_review import coop

    monkeypatch.setattr(
        coop.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "data", ""),
    )
    assert coop._ssh_cat("vm", "/p") == "data"


def test_guest_path_maps_the_clone_to_the_guest_workdir():
    ex = CoopExecutor("vm", host_workdir="/tmp/clone/")
    assert ex.guest_path("/tmp/clone/.git/pr-review/x") == "/workspace/.git/pr-review/x"
    assert ex.guest_path("/elsewhere/x") == "/elsewhere/x"
    assert ex.guest_path("") == ""


def test_host_executor_guest_path_is_the_identity():
    assert HostExecutor().guest_path("/tmp/clone/x") == "/tmp/clone/x"
