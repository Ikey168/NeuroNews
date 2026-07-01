# Pre-import heavy C-extension libs BEFORE coverage's source-package import
# machinery traces them. coverage source tracking + torch._C init crash
# otherwise (SystemError: bad call flags). Importing here (conftest loads at
# session start) makes torch resolve cleanly.
try:
    import torch  # noqa: F401
except Exception:
    pass
