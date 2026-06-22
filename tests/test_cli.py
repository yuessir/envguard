import sys
from unittest.mock import patch, MagicMock
import pytest
from envguard import cli
import os
import json

def test_init_generation_and_idempotency(tmp_path, monkeypatch):
    """Test the dynamic generation of config.json and tools.cache in init, and its idempotency."""
    # 1. Setup mocked HOME
    monkeypatch.setenv("HOME", str(tmp_path))
    
    # 2. Run init for the first time
    args = MagicMock()
    # Mock some basic functions that init relies on, to prevent actual shell execution or exits
    with patch('shutil.which', return_value='/mock/bin/envguard'), \
         patch('envguard.engine.analyze_executable', return_value={'real_path': '/mock/bin/envguard', 'category': 'mock'}):
        cli.init(args)
        
    envguard_dir = tmp_path / ".envguard"
    config_file = envguard_dir / "config.json"
    cache_file = envguard_dir / "tools.cache"
    
    # Verify files were created
    assert config_file.exists(), "config.json should be created on first init"
    assert cache_file.exists(), "tools.cache should be created on first init"
    
    # Verify default content of tools.cache
    cache_content = cache_file.read_text()
    assert "pip" in cache_content
    assert "pytest" in cache_content
    
    # 3. Simulate user modifying config.json
    custom_config = {
        "managed_tools": {
            "installer_tools": ["custom-pip"],
            "execution_tools": ["django-admin"],
            "bypass_tools": ["custom-uv"]
        }
    }
    with open(config_file, "w") as f:
        json.dump(custom_config, f)
        
    # 4. Run init for the second time (Idempotency test)
    with patch('shutil.which', return_value='/mock/bin/envguard'), \
         patch('envguard.engine.analyze_executable', return_value={'real_path': '/mock/bin/envguard', 'category': 'mock'}):
        cli.init(args)
        
    # Verify config.json was NOT overwritten (Idempotency)
    with open(config_file, "r") as f:
        read_config = json.load(f)
    assert "custom-pip" in read_config["managed_tools"]["installer_tools"], "config.json should NOT be overwritten"
    
    # Verify tools.cache WAS updated based on the new config
    new_cache_content = cache_file.read_text()
    assert "custom-pip" in new_cache_content, "tools.cache should be forcefully updated"
    assert "django-admin" in new_cache_content
    assert "pip" not in new_cache_content.split(), "old defaults should be gone"

def test_hook_exec_aligned(capsys):
    mock_args = MagicMock()
    mock_args.command = "pip"
    mock_args.executable = "/path/to/pip"
    
    with patch("envguard.hook.check_alignment", return_value={"aligned": True}):
        cli.hook_exec(mock_args)
    
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""

def test_hook_exec_misaligned(capsys):
    mock_args = MagicMock()
    mock_args.command = "pip"
    mock_args.executable = "/path/to/pip"
    
    msg = "[WARNING] Mismatch!"
    with patch("envguard.hook.check_alignment", return_value={"aligned": False, "message": msg}):
        cli.hook_exec(mock_args)
    
    captured = capsys.readouterr()
    assert msg in captured.err

@patch("builtins.input", return_value="Y")
def test_hook_exec_require_confirmation_yes(mock_input, capsys):
    mock_args = MagicMock()
    mock_args.command = "pip"
    mock_args.executable = "/usr/bin/pip"
    mock_args.python = None
    mock_args.args = ["install", "--break-system-packages"]
    
    msg = "[WARNING] You are using --break-system-packages interactively."
    with patch("envguard.hook.check_alignment", return_value={"aligned": False, "require_confirmation": True, "message": msg}):
        cli.hook_exec(mock_args)
    
    captured = capsys.readouterr()
    # It should not exit, and should ask for Y
    assert "Do you want to proceed anyway?" in captured.err

@patch("builtins.input", return_value="n")
def test_hook_exec_require_confirmation_no(mock_input, capsys):
    mock_args = MagicMock()
    mock_args.command = "pip"
    mock_args.executable = "/usr/bin/pip"
    mock_args.python = None
    mock_args.args = ["install", "--break-system-packages"]
    
    msg = "[WARNING] You are using --break-system-packages interactively."
    with patch("envguard.hook.check_alignment", return_value={"aligned": False, "require_confirmation": True, "message": msg}):
        with pytest.raises(SystemExit) as excinfo:
            cli.hook_exec(mock_args)
        assert excinfo.value.code == 1
    
    captured = capsys.readouterr()
    assert "Do you want to proceed anyway?" in captured.err
    assert "Execution aborted by EnvGuard." in captured.err

def test_doctor(capsys):
    mock_args = MagicMock()
    
    mock_env_data = {
        "original_path": "/path/to/symlink/python",
        "real_path": "/path/to/python",
        "is_venv": True,
        "category": "venv"
    }
    
    mock_subprocess_result = MagicMock()
    mock_subprocess_result.returncode = 0
    mock_subprocess_result.stdout = '{"version": "3.10.0", "prefix": "/mock/prefix", "base_prefix": "/mock/base", "site_packages": "/mock/site"}'
    
    with patch("envguard.engine.analyze_executable", return_value=mock_env_data), \
         patch("shutil.which", return_value="/path/to/pip"), \
         patch("subprocess.run", return_value=mock_subprocess_result), \
         patch("envguard.hook.check_alignment", return_value={"aligned": True}):
        cli.doctor(mock_args)
        
    captured = capsys.readouterr()
    assert "EnvGuard Doctor" in captured.out
    assert "Current Python (Alias): \033[93m/path/to/symlink/python\033[0m" in captured.out
    assert "Current Python (Real):  \033[92m/path/to/python\033[0m" in captured.out
    assert "Version:        3.10.0" in captured.out
    assert "Prefix:         /mock/prefix" in captured.out
    assert "Base Prefix:    /mock/base" in captured.out
    assert "Site-Packages:  /mock/site" in captured.out
    assert "ALIGNED" in captured.out

@pytest.mark.parametrize("pip_loc, pip3_loc", [
    ("global", "venv"),
    ("global", "global"),
    ("venv", "global"),
    ("venv", "venv"),
])
def test_doctor_mixed_alignment_permutations(capsys, pip_loc, pip3_loc):
    # This test proves that the code handles all permutations of:
    # pip (global/venv) and pip3 (global/venv)
    # without getting confused or merging them.
    mock_args = MagicMock()
    
    mock_env_data = {
        "original_path": "/path/to/venv/python",
        "real_path": "/path/to/venv/python",
        "is_venv": True,
        "category": "venv"
    }
    
    def mock_which(cmd):
        if cmd == "pip":
            return "/path/to/venv/pip" if pip_loc == "venv" else "/usr/bin/pip"
        elif cmd == "pip3":
            return "/path/to/venv/pip3" if pip3_loc == "venv" else "/usr/bin/pip3"
        return None
        
    def mock_check_alignment(tool_path, command, active_python=None):
        if command == "pip":
            aligned = (pip_loc == "venv")
            return {
                "aligned": aligned, 
                "tool_category": "venv" if aligned else "system", 
                "message": "" if aligned else "Global pip detected"
            }
        elif command == "pip3":
            aligned = (pip3_loc == "venv")
            return {
                "aligned": aligned, 
                "tool_category": "venv" if aligned else "system", 
                "message": "" if aligned else "Global pip3 detected"
            }
        return {"aligned": True, "tool_category": "unknown", "message": ""}
        
    with patch("envguard.engine.analyze_executable", return_value=mock_env_data), \
         patch("shutil.which", side_effect=mock_which), \
         patch("envguard.hook.check_alignment", side_effect=mock_check_alignment):
        cli.doctor(mock_args)
        
    captured = capsys.readouterr()
    
    # Verify pip
    if pip_loc == "venv":
        assert "- pip (venv): /path/to/venv/pip [\033[92mALIGNED\033[0m]" in captured.out
    else:
        assert "- pip (system): /usr/bin/pip [\033[91mMISALIGNED\033[0m]" in captured.out
        assert "Global pip detected" in captured.err

    # Verify pip3
    if pip3_loc == "venv":
        assert "- pip3 (venv): /path/to/venv/pip3 [\033[92mALIGNED\033[0m]" in captured.out
    else:
        assert "- pip3 (system): /usr/bin/pip3 [\033[91mMISALIGNED\033[0m]" in captured.out
        assert "Global pip3 detected" in captured.err

def test_init_safe_append(tmp_path, capsys):
    import os
    
    # Create mock home and user's .zshrc with existing content
    rc_file = tmp_path / ".zshrc"
    original_content = "export MY_VAR=123\nalias ll='ls -la'\n"
    rc_file.write_text(original_content)
    
    # Mock environment and directories
    with patch("os.environ.get", side_effect=lambda k, d="": "/bin/zsh" if k == "SHELL" else d), \
         patch("os.path.expanduser", return_value=str(tmp_path)), \
         patch("shutil.which", return_value="/path/to/envguard"):
        
        # 1. Run init for the first time
        cli.init(MagicMock())
        
        # Verify output
        captured = capsys.readouterr()
        assert "Initializing EnvGuard" in captured.out
        assert "Successfully injected" in captured.out
        
        # Verify file content is appended, not overwritten
        new_content = rc_file.read_text()
        assert new_content.startswith(original_content)
        assert "# >>> envguard initialize >>>" in new_content
        assert "export PATH=\"/path/to:$PATH\"" in new_content
        
        # 2. Run init a second time to verify idempotency
        cli.init(MagicMock())
        captured_again = capsys.readouterr()
        assert "already exists in" in captured_again.out
        
        # Verify content hasn't been duplicated
        final_content = rc_file.read_text()
        assert final_content == new_content

def test_handle_find_found(capsys, monkeypatch):
    mock_args = MagicMock()
    mock_args.module_name = "cv2"
    mock_args.deep = False
    mock_args.python = None
    
    mock_results = [{
        "path": "/mock/path/cv2",
        "environment": "mock_env",
        "package_name": "opencv-python",
        "package_type": "C-Extension / Bundled Binary",
        "warning": None
    }]
    
    with patch("envguard.cli.scan_for_module", return_value=mock_results):
        cli.find(mock_args)
        
    captured = capsys.readouterr()
    assert "EnvGuard found 'cv2' in the following locations:" in captured.out
    assert "📍 Path: /mock/path/cv2" in captured.out
    assert "Environment: mock_env" in captured.out
    assert "📦 Type: C-Extension / Bundled Binary" in captured.out
    assert "Package: opencv-python" in captured.out

def test_handle_find_not_found(capsys, monkeypatch):
    mock_args = MagicMock()
    mock_args.module_name = "missing_pkg"
    mock_args.deep = True
    mock_args.python = None
    
    with patch("envguard.cli.scan_for_module", return_value=[]):
        cli.find(mock_args)
        
    captured = capsys.readouterr()
    assert "Could not find module 'missing_pkg' in the current scope." in captured.out

def test_main_dispatch(monkeypatch):
    # Test valid dispatch to doctor
    monkeypatch.setattr(sys, "argv", ["envguard", "doctor"])
    with patch("envguard.cli.doctor") as mock_doctor:
        cli.main()
        mock_doctor.assert_called_once()
        
    # Test valid dispatch to find
    monkeypatch.setattr(sys, "argv", ["envguard", "find", "sys"])
    with patch("envguard.cli.find") as mock_find:
        cli.main()
        mock_find.assert_called_once()
        
    # Test valid dispatch to hook-exec
    monkeypatch.setattr(sys, "argv", ["envguard", "hook-exec", "pip", "/bin/pip"])
    with patch("envguard.cli.hook_exec") as mock_hook:
        cli.main()
        mock_hook.assert_called_once()

def test_main_invalid_args(capsys, monkeypatch):
    # Test no args
    monkeypatch.setattr(sys, "argv", ["envguard"])
    with pytest.raises(SystemExit):
        cli.main()
    captured = capsys.readouterr()
    assert "usage:" in captured.out or "usage:" in captured.err

def test_main_keyboard_interrupt(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["envguard", "doctor"])
    with patch("envguard.cli.doctor", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as excinfo:
            cli.main()
        assert excinfo.value.code == 130
        captured = capsys.readouterr()
        assert "Interrupted by user" in captured.err

@patch("envguard.cli.audit")
def test_audit_verbose_flag(mock_audit, monkeypatch):
    """Test that the --verbose flag is correctly parsed for the audit command."""
    monkeypatch.setattr("sys.argv", ["envguard", "audit", "--verbose"])
    cli.main()
    
    mock_audit.assert_called_once()
    args = mock_audit.call_args[0][0]
    assert hasattr(args, "verbose")
    assert args.verbose is True
