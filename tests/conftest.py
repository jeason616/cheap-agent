"""Shared pytest fixtures for cheap-agent tests.

The biggest isolation issue this fixes: tests/test_profiles.py switches
profiles by setting MCP_PROFILE + importlib.reload(config/profiles). That
mutates module-level state and leaks across tests / test runs. The autouse
fixture below snapshots MCP_PROFILE before each test and restores the
modules afterward, so profile tests start from a clean baseline.
"""

import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def restore_profile_state():
    """Snapshot MCP_PROFILE and reload config/profiles back to it after each test.

    Many tool modules capture config values at import time (module-level
    constants), so after a profile test reloads config with a different
    MCP_PROFILE, downstream modules may hold stale values. Reloading them
    back to the original profile at teardown keeps the suite hermetic.
    """
    saved_profile = os.environ.get("MCP_PROFILE")
    yield
    if saved_profile is not None:
        os.environ["MCP_PROFILE"] = saved_profile
    else:
        os.environ.pop("MCP_PROFILE", None)
    # Reload in dependency order so module-level constants reflect the
    # restored profile.
    from cheap_agent import config, profiles
    importlib.reload(config)
    importlib.reload(profiles)
