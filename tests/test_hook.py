import sys
import os
import pytest
from unittest.mock import patch
from envguard import hook

@pytest.mark.parametrize("global_pip_path, expected_category", [
    (os.path.expanduser("~") + "/opt/anaconda3/bin/pip", "conda_workspace_env"),                   # Anaconda
    ("/Library/Developer/CommandLineTools/usr/bin/pip3", "macos_system_env"),      # Xcode default
    ("/usr/local/bin/pip3", "source_compiled"),                          # Source compiled
    (os.path.expanduser("~") + "/.pyenv/versions/3.10.0/bin/pip", "pyenv_versions_env"),          # Pyenv
    (os.path.expanduser("~") + "/Library/Python/3.9/bin/pip", "user_site_env")         # User global
])
def test_check_alignment_complex_global_paths_in_venv(tmp_path, global_pip_path, expected_category):
    # Mock environment: User is inside a standard venv, but pip resolves to various global environments
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "pyvenv.cfg").touch()
    
    venv_python = venv_dir / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.touch()
    (venv_dir / "lib" / "python3.10" / "site-packages").mkdir(parents=True, exist_ok=True)

    # We do not physically create the global_pip_path, engine.py will analyze the string gracefully.
    with patch("sys.executable", str(venv_python)):
        result = hook.check_alignment(global_pip_path, "pip", active_python=str(venv_python))
        assert result.aligned is False
        assert "virtual environment" in result.message
        # The tool category should match our expectation
        assert result.tool_category == expected_category

def test_check_alignment_pip_aligned(tmp_path):
    # Mock environment: sys.executable is in venv, pip is also in the same venv
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "pyvenv.cfg").touch()
    
    venv_python = venv_dir / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.touch()
    (venv_dir / "lib" / "python3.10" / "site-packages").mkdir(parents=True, exist_ok=True)

    venv_pip = venv_dir / "bin" / "pip"
    venv_pip.touch()

    # When trying to run venv pip while venv is active
    with patch("sys.executable", str(venv_python)):
        result = hook.check_alignment(str(venv_pip), "pip")
        assert result.aligned is True

def test_check_alignment_python_m_pip(tmp_path):
    # Mock environment: sys.executable is in venv, and user runs `python3 -m pip`
    # In this case, the tool being executed is python3 itself, which matches the active python perfectly.
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "pyvenv.cfg").touch()
    
    venv_python = venv_dir / "bin" / "python3"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.touch()
    (venv_dir / "lib" / "python3.10" / "site-packages").mkdir(parents=True, exist_ok=True)

    # The shell hook wrapper theoretically doesn't even intercept `python3`, 
    # but if it did (or if we manually check alignment), it should be 100% aligned.
    with patch("sys.executable", str(venv_python)):
        result = hook.check_alignment(str(venv_python), "python3", active_python=str(venv_python))
        assert result.aligned is True

def test_check_alignment_pyinstaller_in_venv(tmp_path):
    # Mock environment: sys.executable is in venv, but pyinstaller is global
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "pyvenv.cfg").touch()
    
    venv_python = venv_dir / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.touch()
    (venv_dir / "lib" / "python3.10" / "site-packages").mkdir(parents=True, exist_ok=True)

    global_pyinstaller = tmp_path / "usr" / "local" / "bin" / "pyinstaller"
    global_pyinstaller.parent.mkdir(parents=True, exist_ok=True)
    global_pyinstaller.touch()

    with patch("sys.executable", str(venv_python)):
        result = hook.check_alignment(str(global_pyinstaller), "pyinstaller", active_python=str(venv_python))
        assert result.aligned is False
        assert "ModuleNotFoundError" in result.message

def test_silent_fail_on_exception():
    # Mock a scenario that raises an exception in the engine
    with patch("envguard.engine.analyze_executable", side_effect=Exception("Permission denied")):
        result = hook.check_alignment("/fake/path", "pip")
        assert result.aligned is True  # Should pass silently

def test_extract_python_version_from_path():
    assert hook.extract_python_version("/Library/Python/3.9/bin/pip") == "3.9"
    assert hook.extract_python_version("/opt/local/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12") == "3.12"
    assert hook.extract_python_version("/usr/bin/pip3") is None

def test_extract_python_version_from_shebang(tmp_path):
    dummy_script = tmp_path / "pip"
    dummy_script.write_text("#!/usr/local/bin/python3.10\nimport sys\n")
    assert hook.extract_python_version(str(dummy_script)) == "3.10"

def test_check_alignment_global_version_mismatch(tmp_path):
    python_path = "/usr/local/bin/python3.12"
    pip_path = "/Library/Python/3.9/bin/pip"
    
    mock_python_env = {"is_venv": False, "category": "macos_system_env", "real_path": python_path}
    mock_pip_env = {"is_venv": False, "category": "user_site_env", "real_path": pip_path}
    
    def mock_analyze(path):
        if path == python_path: return mock_python_env
        return mock_pip_env
        
    with patch("envguard.engine.analyze_executable", side_effect=mock_analyze):
        result = hook.check_alignment(pip_path, "pip", active_python=python_path)
        assert result.aligned is False
        assert "Version Mismatch" in result.message
        assert "3.12" in result.message
        assert "3.9" in result.message
        assert "[HINT]" in result.message
        assert "$PATH" in result.message

def test_check_alignment_global_version_match(tmp_path):
    python_path = "/usr/local/bin/python3.10"
    pip_path = "/Library/Python/3.10/bin/pip"
    
    mock_python_env = {"is_venv": False, "category": "macos_system_env", "real_path": python_path}
    mock_pip_env = {"is_venv": False, "category": "user_site_env", "real_path": pip_path}
    
    def mock_analyze(path):
        if path == python_path: return mock_python_env
        return mock_pip_env
        
    with patch("envguard.engine.analyze_executable", side_effect=mock_analyze):
        result = hook.check_alignment(pip_path, "pip", active_python=python_path)
        assert result.aligned is True

@pytest.mark.parametrize("env_type", ["venv", "global"])
@pytest.mark.parametrize("exec_style", ["pip", "python_m_pip"])
def test_pip_execution_permutations(tmp_path, env_type, exec_style):
    # This test explicitly verifies that using `pip` vs `python -m pip` 
    # works flawlessly (is ALIGNED) as long as you are using the tools 
    # from the current active environment.
    
    if env_type == "venv":
        venv_dir = tmp_path / ".venv"
        venv_dir.mkdir()
        (venv_dir / "pyvenv.cfg").touch()
        python_path = str(venv_dir / "bin" / "python3")
        pip_path = str(venv_dir / "bin" / "pip")
    else:
        python_path = "/usr/local/bin/python3.10"
        pip_path = "/usr/local/bin/pip3.10"
        
    # Write a dummy script to mock the shebang so extract_python_version works for global pip
    if env_type == "global":
        from pathlib import Path
        Path(pip_path).parent.mkdir(parents=True, exist_ok=True)
        Path(pip_path).write_text("#!/usr/local/bin/python3.10\n")
        Path(python_path).write_text("#!/usr/local/bin/python3.10\n")

    # If executing `python -m pip`, the executable intercepted is `python`
    executable_path = python_path if exec_style == "python_m_pip" else pip_path
    command = "python3" if exec_style == "python_m_pip" else "pip"
    
    mock_env = {
        "is_venv": (env_type == "venv"), 
        "category": "venv" if env_type == "venv" else "macos_system_env", 
        "real_path": executable_path,
        "venv_path": str(tmp_path / ".venv") if env_type == "venv" else None
    }
    
    def mock_analyze(path):
        # In this ideal scenario, both python and tool resolve to the same environment properties
        return mock_env
        
    with patch("envguard.engine.analyze_executable", side_effect=mock_analyze):
        result = hook.check_alignment(executable_path, command, active_python=python_path)
        assert result.aligned is True

def test_check_alignment_symlink_abuse(tmp_path):
    # Case: Python is 3.12, but pip is a symlink pointing to 3.9
    python_path = "/usr/local/bin/python3.12"
    pip_symlink_path = "/usr/local/bin/pip"
    pip_real_path = "/usr/bin/pip3.9"
    
    mock_python_env = {"is_venv": False, "category": "macos_system_env", "real_path": python_path}
    mock_pip_env = {"is_venv": False, "category": "macos_system_env", "real_path": pip_real_path}
    
    def mock_analyze(path):
        if path == python_path: return mock_python_env
        return mock_pip_env
        
    with patch("envguard.engine.analyze_executable", side_effect=mock_analyze):
        result = hook.check_alignment(pip_symlink_path, "pip", active_python=python_path)
        assert result.aligned is False
        assert "Version Mismatch" in result.message
        assert "3.12" in result.message
        assert "3.9" in result.message
        assert "[HINT]" in result.message

def test_check_alignment_homebrew_vs_macports(tmp_path):
    # Case: Python is from Homebrew (3.10), Pip is from MacPorts (3.12)
    python_path = "/opt/homebrew/bin/python3.10"
    pip_path = "/opt/local/bin/pip3.12"
    
    mock_python_env = {"is_venv": False, "category": "homebrew_global_env", "real_path": python_path}
    mock_pip_env = {"is_venv": False, "category": "macports_global_env", "real_path": pip_path}
    
    def mock_analyze(path):
        if path == python_path: return mock_python_env
        return mock_pip_env
        
    with patch("envguard.engine.analyze_executable", side_effect=mock_analyze):
        result = hook.check_alignment(pip_path, "pip", active_python=python_path)
        assert result.aligned is False
        assert "Version Mismatch" in result.message
        assert "3.10" in result.message
        assert "3.12" in result.message
        assert "[HINT]" in result.message

def test_check_alignment_uv_bypass():
    mock_python_env = {"is_venv": True, "category": "venv", "real_path": "/venv/python"}
    mock_uv_env = {"is_venv": False, "category": "global", "real_path": "/usr/bin/uv"}
    
    def mock_analyze(path):
        if path == "/venv/python": return mock_python_env
        return mock_uv_env
        
    with patch("envguard.engine.analyze_executable", side_effect=mock_analyze), \
         patch("envguard.engine.get_active_python", return_value="/venv/python"):
        result = hook.check_alignment("/usr/bin/uv", "uv", active_python="/venv/python")
        assert result.aligned is True

def test_check_alignment_different_venvs():
    mock_python_env = {"is_venv": True, "category": "venv", "real_path": "/venv1/python", "venv_path": "/venv1"}
    mock_tool_env = {"is_venv": True, "category": "venv", "real_path": "/venv2/pip", "venv_path": "/venv2"}
    
    def mock_analyze(path):
        if path == "/venv1/python": return mock_python_env
        return mock_tool_env
        
    with patch("envguard.engine.analyze_executable", side_effect=mock_analyze):
        result = hook.check_alignment("/venv2/pip", "pip", active_python="/venv1/python")
        assert result.aligned is False
        assert "Environment mismatch" in result.message

def test_hook_main_execution(capsys, monkeypatch):
    import subprocess
    import json
    # Run the actual script to trigger the __main__ block
    script_path = os.path.join(os.path.dirname(os.path.dirname(hook.__file__)), "hook.py")
    if not os.path.exists(script_path):
        script_path = os.path.join(os.path.dirname(hook.__file__), "hook.py")
        
    res = subprocess.run([sys.executable, script_path, "/usr/bin/pip", "pip"], capture_output=True, text=True)
    
    # Even if it errors (e.g. no active venv), it should output valid JSON because of the silent fail
    assert res.returncode == 0
    try:
        output = json.loads(res.stdout)
        assert "aligned" in output
    except json.JSONDecodeError:
        pytest.fail("Hook output was not valid JSON: " + res.stdout)
