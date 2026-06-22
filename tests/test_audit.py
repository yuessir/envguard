import pytest
import os
from unittest.mock import patch, MagicMock

# The module we are about to implement
from envguard.audit_engine import evaluate_security_status, EnvContext, find_target_python, GhostEnvironmentConflictError

def test_evaluate_security_status():
    """
    TDD Unit Test Matrix for Path Isolation and Corrupted states.
    Tests physical path combinations against sys.prefix and version_str.
    """
    # Active Environment: Python 3.12, Virtual Environment located at /project/.venv
    context_venv = EnvContext(prefix="/project/.venv", version_str="python3.12", is_venv=True)
    
    # Active Environment: Python 3.12, Virtual Environment with CUSTOM name (Duck Typing test)
    context_custom_venv = EnvContext(prefix="/project/my_env", version_str="python3.12", is_venv=True)
    
    # Active Environment: Python 3.12, Global Environment located at /usr/local
    context_global = EnvContext(prefix="/usr/local", version_str="python3.12", is_venv=False)

    # [Test a-2] Venv: flask in venv (SAFE), requests in global (LEAK)
    assert evaluate_security_status("/project/.venv/lib/python3.12/site-packages/flask", context_venv) == "SAFE"
    assert evaluate_security_status("/usr/local/lib/python3.12/site-packages/requests", context_venv) == "LEAK"

    # [Test a-1] Venv Upgrade Leak: flask in venv (SAFE), requests in 3.9 global (LEAK)
    assert evaluate_security_status("/project/.venv/lib/python3.12/site-packages/flask", context_venv) == "SAFE"
    assert evaluate_security_status("/usr/local/lib/python3.9/site-packages/requests", context_venv) == "LEAK"

    # [Test b-2] Venv Only (No upgrade): flask in venv (SAFE)
    assert evaluate_security_status("/project/.venv/lib/python3.12/site-packages/flask", context_venv) == "SAFE"

    # [Test b-1] Venv Corrupted (Upgrade): flask in venv but under old 3.9 folder
    assert evaluate_security_status("/project/.venv/lib/python3.9/site-packages/flask", context_venv) == "CORRUPTED"
    
    # [Test b-1-custom] Venv Corrupted (Custom Venv Name): folder is my_env, no "venv" string in it!
    # Without Duck Typing, this would incorrectly be identified as LEAK instead of CORRUPTED.
    assert evaluate_security_status("/project/my_env/lib/python3.9/site-packages/flask", context_custom_venv) == "CORRUPTED"

    # [Test c-2] Venv Empty, Global Leak (No upgrade)
    assert evaluate_security_status("/usr/local/lib/python3.12/site-packages/flask", context_venv) == "LEAK"

    # [Test c-1] Venv Empty, Global Leak (Upgrade)
    assert evaluate_security_status("/usr/local/lib/python3.9/site-packages/flask", context_venv) == "LEAK"

    # [Test e-2] Global Environment Only (No upgrade)
    assert evaluate_security_status("/usr/local/lib/python3.12/site-packages/flask", context_global) == "SAFE"

    # [Test e-1] Global Environment Leak (Upgrade)
    # The active global is 3.12, but it loaded a package from the 3.9 global path.
    assert evaluate_security_status("/usr/local/lib/python3.9/site-packages/requests", context_global) == "LEAK"


@patch("envguard.audit_engine.os.getcwd")
@patch("envguard.audit_engine.os.environ.get")
@patch("envguard.audit_engine.os.path.exists")
@patch("envguard.audit_engine.engine.get_active_python")
def test_find_target_python_logic(mock_get_active_python, mock_exists, mock_environ_get, mock_getcwd):
    """
    TDD Unit Test Matrix for Traversal & Conflict Logic.
    Tests f-1 to f-4.
    """
    mock_getcwd.return_value = "/project/src"
    mock_get_active_python.return_value = "/usr/local/bin/python3.12"
    
    # helper for os.path.exists
    def mock_exists_side_effect(path):
        if path == "/ProjectA/.venv/pyvenv.cfg":
            return True
        if path == "/ProjectB/.venv/pyvenv.cfg":
            return True
        return False

    mock_exists.side_effect = mock_exists_side_effect

    # [Test f-1] Double Match (Normal)
    # VIRTUAL_ENV points to /ProjectA/.venv
    # Upward traversal also finds /ProjectA/.venv
    mock_environ_get.return_value = "/ProjectA/.venv"
    mock_getcwd.return_value = "/ProjectA/src"
    target_python, target_prefix = find_target_python()
    assert target_prefix == "/ProjectA/.venv"

    # [Test f-2] Ghost Environment Conflict
    # VIRTUAL_ENV points to /ProjectA/.venv
    # Upward traversal finds /ProjectB/.venv
    mock_environ_get.return_value = "/ProjectA/.venv"
    mock_getcwd.return_value = "/ProjectB/src"
    with pytest.raises(GhostEnvironmentConflictError) as exc_info:
        find_target_python()
    assert "Your activated virtualenv" in str(exc_info.value)
    assert "does not match the workspace virtualenv" in str(exc_info.value)

    # [Test f-3] Only Upward Traversal Matches
    # VIRTUAL_ENV is empty
    # Upward traversal finds /ProjectB/.venv
    mock_environ_get.return_value = None
    mock_getcwd.return_value = "/ProjectB/src"
    target_python, target_prefix = find_target_python()
    assert target_prefix == "/ProjectB/.venv"

    # [Test f-4] Fallback to Global
    # VIRTUAL_ENV is empty
    # Upward traversal finds nothing (e.g., in /tmp)
    mock_environ_get.return_value = None
    mock_getcwd.return_value = "/tmp/dir"
    target_python, target_prefix = find_target_python()
    # It should fallback to engine.get_active_python() which we mocked to /usr/local/bin/python3.12
    # In practice, find_target_python might return the python executable and prefix from fallback
    # The prefix for a global python might not be known easily without running it, 
    # but for this test, we just ensure it falls back.
    assert target_python == "/usr/local/bin/python3.12"


def test_ghost_module_detection_probe():
    """
    Integration test for the Ghost Module Detection logic inside the audit probe.
    Injects a fake site-packages directory via PYTHONPATH and verifies that the probe
    correctly flags untracked files as [GHOST], while ignoring whitelisted ones.
    """
    import tempfile
    import sys
    from envguard.audit_engine import run_audit_probe

    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a fake site-packages structure
        fake_site = os.path.join(temp_dir, "lib", "python3.12", "site-packages")
        os.makedirs(fake_site)
        
        # Create a ghost file (should be detected)
        ghost_file = os.path.join(fake_site, "my_ghost_module.py")
        with open(ghost_file, "w") as f:
            f.write("# boo")
            
        # Create a whitelisted file (should be ignored)
        sitecustomize = os.path.join(fake_site, "sitecustomize.py")
        with open(sitecustomize, "w") as f:
            f.write("# ignore me")
            
        # Temporarily inject this fake site into PYTHONPATH so the subprocess probe sees it
        original_pythonpath = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = fake_site
        
        try:
            # Run the actual probe using the current python executable
            result = run_audit_probe(sys.executable)
            
            ghosts = result.get("ghosts", [])
            ghost_names = [g["name"] for g in ghosts]
            
            # The probe should find our injected ghost module
            assert "my_ghost_module" in ghost_names, f"Expected my_ghost_module in ghosts, got {ghost_names}"
            
            # The probe should NOT flag sitecustomize because it's in the whitelist
            assert "sitecustomize" not in ghost_names, "sitecustomize should be ignored"
            
            # The probe should return a warnings list
            assert "warnings" in result, "Probe must return a warnings list"
            assert isinstance(result["warnings"], list), "Warnings must be a list"
            
        finally:
            if original_pythonpath is not None:
                os.environ["PYTHONPATH"] = original_pythonpath
            else:
                del os.environ["PYTHONPATH"]
