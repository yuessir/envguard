import os
import sys
from unittest.mock import patch
from envguard import logger

def test_debug_logger_enabled(capsys):
    # Set the environment variable
    with patch.dict(os.environ, {"ENVGUARD_DEBUG": "1"}):
        logger.debug("Test debug message")
        
    captured = capsys.readouterr()
    assert "[EnvGuard Debug]" in captured.err
    assert "Test debug message" in captured.err

def test_debug_logger_disabled(capsys):
    # Ensure the environment variable is not set
    with patch.dict(os.environ, {}, clear=True):
        logger.debug("Should not print")
        
    captured = capsys.readouterr()
    assert "[EnvGuard Debug]" not in captured.err
    assert "Should not print" not in captured.err
