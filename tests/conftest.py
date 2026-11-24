"""Pytest configuration for fast, deterministic local test execution."""

import pytest

import app.model as app_model

PRODUCTION_PASSWORD_HASH_METHOD = app_model.DEFAULT_PASSWORD_HASH_METHOD


@pytest.fixture(scope='session', autouse=True)
def _fast_test_password_hashing():
    """Use lightweight PBKDF2 rounds during pytest while keeping production at 260,000 rounds."""
    original = app_model.PASSWORD_HASH_METHOD
    app_model.PASSWORD_HASH_METHOD = 'pbkdf2:sha256:1000'
    try:
        yield
    finally:
        app_model.PASSWORD_HASH_METHOD = original
