from unittest import mock
import os
from pathlib import Path
import pytest
from envguard import engine

def test_resolve_real_path(tmp_path):
    # Mock /usr/local/bin/python -> /opt/homebrew/bin/python
    real_dir = tmp_path / "opt" / "homebrew" / "bin"
    real_dir.mkdir(parents=True)
    real_file = real_dir / "python3"
    real_file.touch()

    link_dir = tmp_path / "usr" / "local" / "bin"
    link_dir.mkdir(parents=True)
    link_file = link_dir / "python"
    
    # Create symlink
    os.symlink(real_file, link_file)
    
    assert engine.resolve_real_path(str(link_file)) == str(real_file)

def test_detect_venv(tmp_path):
    # Mock a venv structure
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "pyvenv.cfg").touch()
    
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir()
    python_exec = bin_dir / "python"
    python_exec.touch()
    
    lib_dir = venv_dir / "lib" / "python3.10" / "site-packages"
    lib_dir.mkdir(parents=True)

    assert engine.detect_venv(str(python_exec)) is True

    # Mock non-venv
    global_bin = tmp_path / "usr" / "bin"
    global_bin.mkdir(parents=True)
    global_python = global_bin / "python"
    global_python.touch()

    assert engine.detect_venv(str(global_python)) is False

def test_detect_conda_venv(tmp_path):
    # Mock a Conda venv structure
    conda_dir = tmp_path / "miniconda3" / "envs" / "myenv"
    conda_dir.mkdir(parents=True)
    
    # Conda environments use conda-meta/history instead of pyvenv.cfg
    conda_meta = conda_dir / "conda-meta"
    conda_meta.mkdir()
    (conda_meta / "history").touch()
    
    bin_dir = conda_dir / "bin"
    bin_dir.mkdir()
    python_exec = bin_dir / "python"
    python_exec.touch()
    
    # Must have lib/pythonX.X/site-packages
    lib_dir = conda_dir / "lib" / "python3.10" / "site-packages"
    lib_dir.mkdir(parents=True)

    assert engine.detect_venv(str(python_exec)) is True

def test_detect_uv_venv(tmp_path):
    # UV creates PEP 405 compliant virtual environments.
    # It also might use hardlinks or copy depending on OS, but always creates pyvenv.cfg
    uv_venv_dir = tmp_path / ".venv"
    uv_venv_dir.mkdir()
    
    # pyvenv.cfg is present
    cfg = uv_venv_dir / "pyvenv.cfg"
    cfg.write_text("home = /opt/homebrew/bin\ninclude-system-site-packages = false\nversion = 3.12.0\nexecutable = /opt/homebrew/bin/python3.12\ncommand = /opt/homebrew/bin/python3.12 -m venv /path/to/.venv\n")
    
    bin_dir = uv_venv_dir / "bin"
    bin_dir.mkdir()
    
    # executable inside bin
    python_exec = bin_dir / "python"
    python_exec.touch()
    
    lib_dir = uv_venv_dir / "lib" / "python3.12" / "site-packages"
    lib_dir.mkdir(parents=True)
    
    # UV also installs the 'uv' binary in the environment or user might use global uv.
    # The key is that detect_venv correctly identifies the python executable inside it as a venv.
    assert engine.detect_venv(str(python_exec)) is True

def test_categorize_path():
    # Test Homebrew path
    assert engine.categorize_path("/opt/homebrew/bin/python3") == "homebrew_global_env"
    assert engine.categorize_path("/usr/local/Cellar/python/3.11/bin/python") == "homebrew_global_env"

    # Test MacPorts path
    assert engine.categorize_path("/opt/local/bin/python3") == "macports_global_env"
    assert engine.categorize_path("/opt/local/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages") == "macports_global_env"

    # Test Pyenv path
    assert engine.categorize_path(os.path.expanduser("~") + "/.pyenv/versions/3.10.0/bin/python") == "pyenv_versions_env"

    # Test System default path
    assert engine.categorize_path("/usr/bin/python3") == "macos_system_env"
    assert engine.categorize_path("/Library/Developer/CommandLineTools/usr/bin/python3") == "macos_system_env"

    # Test Conda path
    assert engine.categorize_path(os.path.expanduser("~") + "/opt/anaconda3/bin/python") == "conda_workspace_env"
    assert engine.categorize_path(os.path.expanduser("~") + "/miniconda3/bin/python") == "conda_workspace_env"
    
    # Test User Global path
    assert engine.categorize_path(os.path.expanduser("~") + "/Library/Python/3.9/bin/pip") == "user_site_env"
    assert engine.categorize_path(os.path.expanduser("~") + "/.local/bin/pip") == "user_site_env"
    
    # Unknown path
    assert engine.categorize_path("/some/random/path/python") == "unknown"

def test_analyze_executable_venv(tmp_path):
    venv_dir = tmp_path / "myenv"
    venv_dir.mkdir()
    (venv_dir / "pyvenv.cfg").touch()
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir()
    python_exec = bin_dir / "python"
    python_exec.touch()
    lib_dir = venv_dir / "lib" / "python3.10" / "site-packages"
    lib_dir.mkdir(parents=True)

    result = engine.analyze_executable(str(python_exec))
    assert result["is_venv"] is True
    assert result["category"] == "venv"
    assert result["real_path"] == str(python_exec)

def test_analyze_executable_source_compiled(tmp_path):
    bin_dir = tmp_path / "usr" / "local" / "bin"
    bin_dir.mkdir(parents=True)
    python_exec = bin_dir / "python3"
    python_exec.touch()

    # Need to patch the path check inside analyze_executable since we use tmp_path
    result = engine.analyze_executable(str(python_exec), _override_usr_local_bin=str(bin_dir))
    assert result["is_venv"] is False
    assert result["category"] == "source_compiled"

@mock.patch("envguard.engine.load_rules")
def test_analyze_executable_homebrew(mock_load_rules, tmp_path):
    mock_load_rules.return_value = {
        "environments": [{"id": "homebrew_global_env", "path_patterns": [str(tmp_path / "opt" / "homebrew" / "lib" / "python3" / "site-packages")]}]
    }
    # Setup Homebrew path and symlink
    real_dir = tmp_path / "opt" / "homebrew" / "bin"
    real_dir.mkdir(parents=True)
    real_file = real_dir / "python3"
    real_file.touch()

    link_dir = tmp_path / "usr" / "local" / "bin"
    link_dir.mkdir(parents=True)
    link_file = link_dir / "python3"
    
    os.symlink(real_file, link_file)

    result = engine.analyze_executable(str(link_file), _override_usr_local_bin=str(link_dir))
    assert result["is_venv"] is False
    assert result["category"] == "homebrew_global_env"
    assert result["real_path"] == str(real_file)

def test_get_active_python(monkeypatch):
    import sys
    monkeypatch.setattr("shutil.which", lambda x: "/mocked/python" if x == "python3" else None)
    assert engine.get_active_python() == "/mocked/python"
    
    monkeypatch.setattr("shutil.which", lambda x: None)
    assert engine.get_active_python() == sys.executable

def test_load_rules_exception(monkeypatch):
    monkeypatch.setattr("builtins.open", mock.Mock(side_effect=Exception("mocked err")))
    assert engine.load_rules() == {"environments": [], "managed_tools": {}}

def test_resolve_real_path_exceptions(tmp_path):
    # Test bash shim exception
    shim_file = tmp_path / "shim.sh"
    shim_file.write_text("bash\nsome text")
    
    with mock.patch("subprocess.run", side_effect=Exception("sub err")):
        assert engine.resolve_real_path(str(shim_file)) != ""
        
    # Test general exception (e.g. os.path.realpath raises)
    with mock.patch("os.path.realpath", side_effect=Exception("os err")):
        assert engine.resolve_real_path(str(shim_file)) == str(shim_file)

def test_detect_venv_exception():
    with mock.patch("os.path.dirname", side_effect=Exception("dir err")):
        assert engine.detect_venv("invalid") is False

def test_categorize_path_direct_match():
    with mock.patch("envguard.engine.load_rules", return_value={"environments": [{"id": "exact", "path_patterns": ["/exact/path"]}]}):
        assert engine.categorize_path("/exact/path") == "exact"
        assert engine.categorize_path("/exact/path/sub") == "exact"
