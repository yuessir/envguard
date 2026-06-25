import pytest
import os
from unittest.mock import patch, MagicMock

# The module we are about to implement
from envguard.audit_engine import evaluate_security_status, EnvContext, find_target_python, GhostEnvironmentConflictError

class TestAuditIntegrationMatrix:
    """
    14 E2E Integration Tests covering VIRTUAL_ENV activation status, Python upgrades,
    and different leak/corruption boundaries.
    """
    
    def _run_integration(self, is_activated: bool, has_venv: bool, active_python_version: str, package_path: str) -> str:
        """
        Helper to simulate the engine logic:
        1. find_target_python()
        2. evaluate_security_status()
        """
        with patch("envguard.audit_engine.os.environ.get") as mock_environ_get, \
             patch("envguard.audit_engine.os.getcwd") as mock_getcwd, \
             patch("envguard.audit_engine.os.path.exists") as mock_exists, \
             patch("envguard.audit_engine.engine.get_active_python") as mock_get_active_python:
            
            if is_activated:
                mock_environ_get.return_value = "/project/.venv"
                mock_getcwd.return_value = "/project/src"
                mock_get_active_python.return_value = f"/project/.venv/bin/{active_python_version}"
                def exists_side_effect(path):
                    return path == "/project/.venv/pyvenv.cfg"
                mock_exists.side_effect = exists_side_effect
            else:
                mock_environ_get.return_value = None
                if has_venv:
                    mock_getcwd.return_value = "/project/src"
                    mock_get_active_python.return_value = f"/usr/local/bin/{active_python_version}"
                    def exists_side_effect(path):
                        return path == "/project/.venv/pyvenv.cfg"
                    mock_exists.side_effect = exists_side_effect
                else:
                    mock_getcwd.return_value = "/tmp/dir"
                    mock_get_active_python.return_value = f"/usr/local/bin/{active_python_version}"
                    mock_exists.return_value = False
                    
            # Step 1: Context Resolution
            target_python, target_prefix = find_target_python()
            
            # Build EnvContext based on resolution
            if target_prefix:
                context = EnvContext(prefix=target_prefix, version_str=active_python_version, is_venv=True)
            else:
                context = EnvContext(prefix="/usr/local", version_str=active_python_version, is_venv=False)
                
            # Step 2: Path Evaluation
            return evaluate_security_status(package_path, context)

    # ==============================================================================
    # 🍎 第一類：無虛擬環境 (Global Only)
    # ==============================================================================
    def test_global_upgrade_leak(self):
        # 1. 套件全在全局，涉及 Python 升級
        # Active: python3.12, loaded: python3.9 package
        res = self._run_integration(is_activated=False, has_venv=False, active_python_version="python3.12", package_path="/usr/local/lib/python3.9/site-packages/requests")
        assert res == "LEAK"

    def test_global_no_upgrade(self):
        # 2. 套件全在全局，沒升級
        res = self._run_integration(is_activated=False, has_venv=False, active_python_version="python3.12", package_path="/usr/local/lib/python3.12/site-packages/flask")
        assert res == "SAFE"

    # ==============================================================================
    # 🍏 第二類：有虛擬環境 (情境 A - 套件全在全局，Venv 為空)
    # ==============================================================================
    def test_venv_empty_global_leak_upgrade_activated(self):
        # 3. 涉及升級 + 已啟動 Venv
        res = self._run_integration(is_activated=True, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.9/site-packages/flask")
        assert res == "LEAK"

    def test_venv_empty_global_leak_upgrade_not_activated(self):
        # 4. 涉及升級 + 未啟動 Venv (引擎將向上推演)
        res = self._run_integration(is_activated=False, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.9/site-packages/flask")
        assert res == "LEAK"

    def test_venv_empty_global_leak_no_upgrade_activated(self):
        # 5. 沒升級 + 已啟動 Venv
        res = self._run_integration(is_activated=True, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.12/site-packages/flask")
        assert res == "LEAK"

    def test_venv_empty_global_leak_no_upgrade_not_activated(self):
        # 6. 沒升級 + 未啟動 Venv (引擎將向上推演)
        res = self._run_integration(is_activated=False, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.12/site-packages/flask")
        assert res == "LEAK"

    # ==============================================================================
    # 🍏 第二類：有虛擬環境 (情境 B - 套件全在虛擬，全局為空)
    # ==============================================================================
    def test_venv_only_corrupted_upgrade_activated(self):
        # 7. 涉及升級導致損壞 + 已啟動 Venv
        res = self._run_integration(is_activated=True, has_venv=True, active_python_version="python3.12", package_path="/project/.venv/lib/python3.9/site-packages/flask")
        assert res == "CORRUPTED"

    def test_venv_only_corrupted_upgrade_not_activated(self):
        # 8. 涉及升級導致損壞 + 未啟動 Venv
        res = self._run_integration(is_activated=False, has_venv=True, active_python_version="python3.12", package_path="/project/.venv/lib/python3.9/site-packages/flask")
        assert res == "CORRUPTED"

    def test_venv_only_no_upgrade_activated(self):
        # 9. 沒升級 (完美隔離) + 已啟動 Venv
        res = self._run_integration(is_activated=True, has_venv=True, active_python_version="python3.12", package_path="/project/.venv/lib/python3.12/site-packages/flask")
        assert res == "SAFE"

    def test_venv_only_no_upgrade_not_activated(self):
        # 10. 沒升級 (完美隔離) + 未啟動 Venv
        res = self._run_integration(is_activated=False, has_venv=True, active_python_version="python3.12", package_path="/project/.venv/lib/python3.12/site-packages/flask")
        assert res == "SAFE"

    # ==============================================================================
    # 🍏 第二類：有虛擬環境 (情境 C - 混合污染)
    # ==============================================================================
    def test_venv_mixed_upgrade_activated(self):
        # 11. 涉及升級，部分套件讀到全局 + 已啟動 Venv
        res = self._run_integration(is_activated=True, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.9/site-packages/requests")
        assert res == "LEAK"

    def test_venv_mixed_upgrade_not_activated(self):
        # 12. 涉及升級，部分套件讀到全局 + 未啟動 Venv
        res = self._run_integration(is_activated=False, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.9/site-packages/requests")
        assert res == "LEAK"

    def test_venv_mixed_no_upgrade_activated(self):
        # 13. 沒升級，部分套件讀到全局 + 已啟動 Venv
        res = self._run_integration(is_activated=True, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.12/site-packages/requests")
        assert res == "LEAK"

    def test_venv_mixed_no_upgrade_not_activated(self):
        # 14. 沒升級，部分套件讀到全局 + 未啟動 Venv
        res = self._run_integration(is_activated=False, has_venv=True, active_python_version="python3.12", package_path="/usr/local/lib/python3.12/site-packages/requests")
        assert res == "LEAK"


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

def test_evaluate_wrapper_status_false_positives():
    from envguard.audit_engine import evaluate_wrapper_status, EnvContext
    
    context = EnvContext(prefix="/Users/test/.venv", version_str="3.12", is_venv=True)
    # The shebang matches the prefix literally, even if realpath resolves outside
    wrapper_info = {
        "shebang_path": "/Users/test/.venv/bin/python3.12"
    }
    
    assert evaluate_wrapper_status(wrapper_info, context) == "SAFE"

def test_evaluate_wrapper_status_corrupted():
    from envguard.audit_engine import evaluate_wrapper_status, EnvContext
    from unittest.mock import patch
    
    context = EnvContext(prefix="/Users/test/Python/3.13", version_str="3.13", is_venv=False)
    # The shebang points strictly outside
    wrapper_info = {
        "shebang_path": "/opt/local/bin/python3"
    }
    
    with patch("os.path.realpath", return_value="/opt/local/bin/python3.12"):
        assert evaluate_wrapper_status(wrapper_info, context) == "CORRUPTED_WRAPPER"
