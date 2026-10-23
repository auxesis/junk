"""Run reviews inside an isolated coop microVM."""

MIN_VCPUS, MAX_VCPUS = 2, 8
MIN_MEM_MIB, MAX_MEM_MIB = 4096, 12288
MEM_PER_JOB_MIB = 1536


def vm_size(job_count: int) -> tuple[int, int]:
    """Return (vcpus, mem_mib) for a VM that runs `job_count` jobs."""
    vcpus = min(max(job_count, MIN_VCPUS), MAX_VCPUS)
    mem_mib = min(max(job_count * MEM_PER_JOB_MIB, MIN_MEM_MIB), MAX_MEM_MIB)
    return vcpus, mem_mib
