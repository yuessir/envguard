from unittest import mock
from envguard import engine

def test_phase2_detect_venv_duck_typing(tmp_path):
    # Valid PEP 405 venv
    venv_dir = tmp_path / "myenv"
    bin_dir = venv_dir / "bin"
    lib_dir = venv_dir / "lib" / "python3.10" / "site-packages"
    
    bin_dir.mkdir(parents=True)
    lib_dir.mkdir(parents=True)
    
    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    pyvenv_cfg.write_text("home = /usr/bin")
    
    python_exe = bin_dir / "python"
    python_exe.touch()
    
    assert engine.detect_venv(str(python_exe)) is True

def test_phase2_detect_venv_invalid(tmp_path):
    # Missing lib dir
    venv_dir = tmp_path / "invalidenv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)
    
    pyvenv_cfg = venv_dir / "pyvenv.cfg"
    pyvenv_cfg.write_text("home = /usr/bin")
    
    python_exe = bin_dir / "python"
    python_exe.touch()
    
    assert engine.detect_venv(str(python_exe)) is False

@mock.patch("envguard.engine.load_rules")
def test_phase2_categorize_path_rules(mock_load_rules):
    mock_load_rules.return_value = {
        "environments": [
            {
                "id": "my_custom_env",
                "path_patterns": ["/opt/custom/lib/python*/site-packages"]
            }
        ]
    }
    # Test base path extraction
    # /opt/custom/bin/python should match base of /opt/custom/lib/python*/site-packages
    assert engine.categorize_path("/opt/custom/bin/python") == "my_custom_env"
    
    # Test unknown
    assert engine.categorize_path("/usr/local/bin/node") == "unknown"

def test_phase2_resolve_real_path_pyenv_shim(tmp_path):
    shim = tmp_path / "python"
    shim.write_text("#!/usr/bin/env bash\nexec pyenv exec \"$@\"")
    
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "/users/fake/.pyenv/versions/3.10.0/bin/python\n"
        
        real_path = engine.resolve_real_path(str(shim))
        assert real_path == "/users/fake/.pyenv/versions/3.10.0/bin/python"

@mock.patch("shutil.which")
def test_get_active_python(mock_which):
    import sys
    # When shutil.which finds python3 in PATH
    mock_which.side_effect = lambda x: "/mock/path/to/python3" if x == "python3" else None
    assert engine.get_active_python() == "/mock/path/to/python3"
    
    # When shutil.which only finds python in PATH
    mock_which.side_effect = lambda x: "/mock/path/to/python" if x == "python" else None
    assert engine.get_active_python() == "/mock/path/to/python"
    
    # When shutil.which finds neither, it falls back to sys.executable
    mock_which.side_effect = lambda x: None
    assert engine.get_active_python() == sys.executable
