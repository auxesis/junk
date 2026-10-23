from pr_review.coop import vm_size


def test_vm_size_scales_with_jobs_within_caps():
    assert vm_size(1) == (2, 4096)  # floors apply
    assert vm_size(3) == (3, 4608)  # 3 vcpus, 3*1536 mem
    assert vm_size(20) == (8, 12288)  # ceilings apply


def test_vm_size_treats_zero_jobs_as_the_floor():
    assert vm_size(0) == (2, 4096)
