# Loaded from a venv .pth file. Do not name this sitecustomize.py:
# Ubuntu ships /usr/lib/python3.14/sitecustomize.py and that wins.
#
# Cache AMD SMI GPU handles before torch initializes HIP.
# vLLM 0.23 ROCm infers the platform from amdsmi_get_processor_handles().
# On Ubuntu 26.04 / ROCm 10.1.0 / torch 2.13+rocm10.1.0, importing torch first
# makes that call return [] (and torch.cuda.device_count() stays 0 even
# though hipGetDeviceCount is 1 and torch.zeros(..., device="cuda") works).
# Result: UnspecifiedPlatform and
# "Failed to infer device type" during argparse default construction.
try:
    import amdsmi

    amdsmi.amdsmi_init()
    try:
        _HANDLES = list(amdsmi.amdsmi_get_processor_handles() or [])
    finally:
        try:
            amdsmi.amdsmi_shut_down()
        except Exception:
            pass
    _orig_handles = amdsmi.amdsmi_get_processor_handles

    def _handles():
        try:
            found = _orig_handles()
            if found:
                return found
        except Exception:
            pass
        return _HANDLES

    amdsmi.amdsmi_get_processor_handles = _handles
except Exception:
    pass

try:
    import torch

    _device_count = torch.cuda.device_count

    def _patched_device_count():
        count = _device_count()
        if count > 0:
            return count
        if getattr(torch.version, "hip", None) and torch.cuda.is_available():
            return 1
        return count

    torch.cuda.device_count = _patched_device_count
except Exception:
    pass
