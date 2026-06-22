import os
import json
import pytest
from unittest.mock import patch
from envguard import engine

def test_get_managed_tools_fallback(tmp_path, monkeypatch):
    """Test that if ~/.envguard/config.json doesn't exist, we fallback to rules.json."""
    monkeypatch.setenv("HOME", str(tmp_path))
    
    tools = engine.get_managed_tools()
    
    # Should fallback to the ones defined in rules.json
    assert "pip" in tools.get("installer_tools", [])
    assert "pytest" in tools.get("execution_tools", [])
    assert "uv" in tools.get("bypass_tools", [])

def test_get_managed_tools_custom_override(tmp_path, monkeypatch):
    """Test that if ~/.envguard/config.json exists, it correctly overrides."""
    monkeypatch.setenv("HOME", str(tmp_path))
    
    envguard_dir = tmp_path / ".envguard"
    envguard_dir.mkdir()
    
    config_file = envguard_dir / "config.json"
    custom_config = {
        "managed_tools": {
            "installer_tools": ["custom-pip"],
            "execution_tools": ["django-admin"],
            "bypass_tools": ["custom-uv"]
        }
    }
    
    with open(config_file, "w") as f:
        json.dump(custom_config, f)
        
    tools = engine.get_managed_tools()
    
    assert "custom-pip" in tools.get("installer_tools", [])
    assert "pip" not in tools.get("installer_tools", [])
    assert "django-admin" in tools.get("execution_tools", [])
