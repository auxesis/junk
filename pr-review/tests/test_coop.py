from types import SimpleNamespace

import pytest

from pr_review.coop import CoopUnavailable, preflight, vm_name, vm_size


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
