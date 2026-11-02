from __future__ import annotations

import sys

import pytest

from autoclip import secure


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI hanya Windows")
def test_dpapi_roundtrip():
    data = b"refresh-token-rahasia"
    encrypted = secure.protect(data)
    assert encrypted != data
    assert secure.unprotect(encrypted) == data
