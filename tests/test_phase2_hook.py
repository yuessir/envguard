from unittest import mock
from envguard import hook

@mock.patch("sys.stdout.isatty")
@mock.patch("envguard.engine.analyze_executable")
def test_break_system_packages_interactive(mock_analyze, mock_isatty):
    mock_isatty.return_value = True
    mock_analyze.return_value = {"is_venv": False, "category": "system_global", "real_path": "/usr/bin/pip"}
    
    result = hook.check_alignment("/usr/bin/pip", "pip", args=["install", "--break-system-packages"])
    assert result.abort is False
    assert "[WARNING]" in result.message

@mock.patch("sys.stdout.isatty")
@mock.patch("envguard.engine.analyze_executable")
def test_break_system_packages_non_interactive(mock_analyze, mock_isatty):
    mock_isatty.return_value = False
    mock_analyze.return_value = {"is_venv": False, "category": "system_global", "real_path": "/usr/bin/pip"}
    
    result = hook.check_alignment("/usr/bin/pip", "pip", args=["install", "--break-system-packages"])
    assert result.abort is True
    assert "[DANGER]" in result.message
