from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.config import ConfigError, load_config

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config.example.yaml"

def test_first_run_persists_generated_key(tmp_path, caplog):
    config_path = tmp_path / "config.yaml"

    with caplog.at_level(logging.INFO):
        config = load_config(config_path, example_path=EXAMPLE_CONFIG, environ={})

    persisted_key = config_path.read_text(encoding="utf-8")
    assert len(config.security.admin_key) >= 32
    assert config.security.admin_key in persisted_key
    assert config.security.admin_key in caplog.text
    assert config_path.stat().st_mode & 0o077 == 0


def test_unwritable_config_uses_and_prints_an_in_memory_key(tmp_path, caplog):
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("block directory creation", encoding="utf-8")
    config_path = parent_file / "config.yaml"

    with caplog.at_level(logging.WARNING):
        config = load_config(config_path, example_path=EXAMPLE_CONFIG, environ={})

    assert len(config.security.admin_key) >= 32
    assert "using an in-memory admin key" in caplog.text
    assert config.security.admin_key in caplog.text
    assert not config_path.exists()


def test_environment_key_overrides_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    example_path = EXAMPLE_CONFIG
    config_path.write_text("security:\n  admin_key: file-key\n", encoding="utf-8")

    config = load_config(
        config_path, example_path=example_path, environ={"GAME_ADMIN_KEY": "environment-key"}
    )

    assert config.security.admin_key == "environment-key"


def test_invalid_values_and_unknown_keys_are_rejected(tmp_path):
    config_path = tmp_path / "config.yaml"
    example_path = EXAMPLE_CONFIG
    config_path.write_text("server:\n  port: 70000\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="server.port"):
        load_config(config_path, example_path=example_path, environ={"GAME_ADMIN_KEY": "test-key"})

    config_path.write_text("games:\n  unexpected: true\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Unknown configuration key"):
        load_config(config_path, example_path=example_path, environ={"GAME_ADMIN_KEY": "test-key"})
