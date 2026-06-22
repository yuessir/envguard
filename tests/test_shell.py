import subprocess
import pytest
import shutil
from pathlib import Path

def get_script_path(shell_type):
    # shell_type is 'bash' or 'zsh'
    base_dir = Path(__file__).parent.parent
    if shell_type == 'zsh':
        return base_dir / "src" / "envguard" / "shell" / "envguard.plugin.zsh"
    else:
        return base_dir / "src" / "envguard" / "shell" / "envguard.bash"

@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_shell_hook_preserves_alias(shell):
    if not shutil.which(shell):
        pytest.skip(f"{shell} is not installed on this system.")
        
    script_path = get_script_path(shell)
    
    # We create a small script that defines an alias, sources envguard, and runs the alias.
    # We use pip to echo a specific string so we know the alias wasn't destroyed.
    test_script = f"""
    alias pip="echo MY_CUSTOM_ALIAS"
    source "{script_path}"
    eval "pip"
    """
    
    if shell == "zsh":
        cmd_args = ["zsh", "-c", "setopt aliases;\n" + test_script]
    else:
        cmd_args = ["bash", "-O", "expand_aliases", "-c", test_script]
        
    result = subprocess.run(
        cmd_args,
        capture_output=True,
        text=True
    )
    
    # 1. Check that EnvGuard printed the warning to stderr containing the alias definition
    assert "EnvGuard Warning" in result.stderr
    assert "Detected alias for 'pip'" in result.stderr
    assert "pip=" in result.stderr  # The actual alias definition string should be printed
    assert "MY_CUSTOM_ALIAS" in result.stderr
    
    # 2. Check that the alias actually survived and executed
    assert "MY_CUSTOM_ALIAS" in result.stdout

@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_shell_hook_preserves_function(shell):
    if not shutil.which(shell):
        pytest.skip(f"{shell} is not installed on this system.")
        
    script_path = get_script_path(shell)
    
    # We create a small script that defines a function, sources envguard, and runs the function.
    test_script = f"""
    function pip() {{
        echo "MY_CUSTOM_FUNCTION"
    }}
    source "{script_path}"
    pip
    """
    
    cmd_args = [shell, "-c", test_script]
        
    result = subprocess.run(
        cmd_args,
        capture_output=True,
        text=True
    )
    
    # 1. Check that EnvGuard printed the warning to stderr
    assert "EnvGuard Warning" in result.stderr
    assert "Detected existing shell function for 'pip'" in result.stderr
    
    # 2. Check that the function actually survived and executed
    assert "MY_CUSTOM_FUNCTION" in result.stdout

@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_shell_hook_normal_execution(shell, tmp_path):
    if not shutil.which(shell):
        pytest.skip(f"{shell} is not installed on this system.")
        
    script_path = get_script_path(shell)

    # Create a real dummy executable in PATH so `command pip` succeeds
    dummy_bin = tmp_path / "bin"
    dummy_bin.mkdir()
    dummy_pip = dummy_bin / "pip"
    dummy_pip.write_text("#!/bin/sh\necho 'SYSTEM_PIP'")
    dummy_pip.chmod(0o755)
    
    test_script = f"""
    export PATH="{dummy_bin}:$PATH"
    unalias pip 2>/dev/null || true
    source "{script_path}"
    pip
    """

    result = subprocess.run(
        [shell, "-c", test_script],
        capture_output=True,
        text=True
    )
    
    # 1. No warning should be printed
    assert "EnvGuard Warning" not in result.stderr
    
    # 2. It should have hooked it. (If EnvGuard CLI is not in path, the hook will just execute the underlying command)
    # But since we defined pip as a function, the hook wrapper `command pip` won't find it easily unless we made a real file.
    # So as long as it didn't error out and warning didn't show, the hook installed successfully.
    assert result.returncode == 0
