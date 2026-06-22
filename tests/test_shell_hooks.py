import os
import subprocess
import time
import pytest
from pathlib import Path

def setup_mock_env(tmp_path: Path):
    """Setup a mocked environment for shell testing."""
    envguard_home = tmp_path / ".envguard"
    envguard_home.mkdir()
    
    config_file = envguard_home / "config.json"
    cache_file = envguard_home / "tools.cache"
    
    # Create an old cache file
    cache_file.write_text("pip pip3")
    
    # Wait a bit to ensure mtime difference
    time.sleep(0.01)
    
    # Create a newer config.json
    config_file.write_text('{"managed_tools": {}}')
    
    # Mock envguard binary in PATH
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mock_bin = bin_dir / "envguard"
    mock_bin.write_text("#!/bin/sh\necho 'Mock EnvGuard Executed: '$@")
    mock_bin.chmod(0o755)
    
    return envguard_home, bin_dir

@pytest.mark.parametrize("shell,script_name", [
    ("bash", "envguard.bash"),
    ("zsh", "envguard.plugin.zsh")
])
def test_shell_wrapper_out_of_sync_warning(tmp_path, shell, script_name):
    """Test that running 'envguard find' prints the out-of-sync warning."""
    # Skip if shell is not installed on the system
    if not subprocess.run(["which", shell], capture_output=True).returncode == 0:
        pytest.skip(f"{shell} is not installed")

    envguard_home, bin_dir = setup_mock_env(tmp_path)
    
    # Path to the actual script we want to test
    script_path = Path(__file__).parent.parent / "src" / "envguard" / "shell" / script_name
    
    # Build the shell command to source the script and call the wrapper
    # We set HOME to tmp_path so the script looks for ~/.envguard inside our sandbox
    cmd = f"""
    export HOME="{tmp_path}"
    export PATH="{bin_dir}:$PATH"
    source "{script_path}"
    envguard find
    """
    
    result = subprocess.run([shell, "-c", cmd], capture_output=True, text=True)
    
    # 1. The wrapper should call the mock binary
    assert "Mock EnvGuard Executed: find" in result.stdout
    # 2. The out-of-sync warning should be in stderr
    assert "config.json has been modified" in result.stderr
    assert "Run 'envguard init'" in result.stderr

@pytest.mark.parametrize("shell,script_name", [
    ("bash", "envguard.bash"),
    ("zsh", "envguard.plugin.zsh")
])
def test_shell_wrapper_init_hot_reload(tmp_path, shell, script_name):
    """Test that running 'envguard init' skips the warning and hot-reloads."""
    if not subprocess.run(["which", shell], capture_output=True).returncode == 0:
        pytest.skip(f"{shell} is not installed")

    envguard_home, bin_dir = setup_mock_env(tmp_path)
    
    # To test the hot-reload, we also need to copy the script into ~/.envguard/ so the wrapper can source it
    script_path = Path(__file__).parent.parent / "src" / "envguard" / "shell" / script_name
    dest_script = envguard_home / script_name
    dest_script.write_text(script_path.read_text())
    
    cmd = f"""
    export HOME="{tmp_path}"
    export PATH="{bin_dir}:$PATH"
    source "{script_path}"
    envguard init
    """
    
    result = subprocess.run([shell, "-c", cmd], capture_output=True, text=True)
    
    # 1. The wrapper should call the mock binary
    assert "Mock EnvGuard Executed: init" in result.stdout
    # 2. The out-of-sync warning should NOT be printed
    assert "config.json has been modified" not in result.stderr
    # 3. The hot-reload success message should be printed
    assert "Hot-reloaded shell hooks" in result.stderr
