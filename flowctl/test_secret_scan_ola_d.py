"""T21: casos controlados secret scan placeholders extra."""
from __future__ import annotations

import os

import pytest

from flowctl.secret_scan import secret_value_looks_placeholder


def test_extra_placeholder_substrings_reduce_fp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOW_SECRET_SCAN_EXTRA_PLACEHOLDER_SUBSTRINGS", "acme-ui-token")
    assert secret_value_looks_placeholder("secret password: acme-ui-token-demo-value") is True
