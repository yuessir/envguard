import os
from envguard import find_engine

def test_detect_shadowing(tmp_path):
    # Setup shadowing file
    shadow_file = tmp_path / "email.py"
    shadow_file.touch()
    
    result = find_engine.detect_shadowing("email", str(tmp_path))
    assert result is not None
    assert "shadowing" in result[0]
    assert result[1] == str(shadow_file)

    # Setup non-shadowing
    assert find_engine.detect_shadowing("requests", str(tmp_path)) is None

def test_detect_shadowing_dir(tmp_path):
    shadow_dir = tmp_path / "sys"
    shadow_dir.mkdir()
    (shadow_dir / "__init__.py").touch()
    
    result = find_engine.detect_shadowing("sys", str(tmp_path))
    assert result is not None
    assert "shadowing" in result[0]
    assert result[1] == str(shadow_dir)

def test_get_global_paths_includes_macports_frameworks():
    # TDD Test: Ensure the real rules.json includes the MacPorts Frameworks path
    # Without this, Phase 3 will completely miss global OpenCV and other packages.
    paths = find_engine.get_global_paths()
    expected_path = os.path.expanduser("/opt/local/Library/Frameworks/Python.framework/Versions/*/lib/python*/site-packages")
    assert expected_path in paths, "rules.json is missing the MacPorts Frameworks path pattern!"

def test_get_current_venv_paths(tmp_path, monkeypatch):
    from envguard import engine
    monkeypatch.setattr(engine, "detect_venv", lambda x: True)
    
    # Create fake venv structure
    env_dir = tmp_path / "venv"
    lib_dir = env_dir / "lib" / "python3.12" / "site-packages"
    lib_dir.mkdir(parents=True)
    
    fake_python = str(env_dir / "bin" / "python")
    paths = find_engine.get_current_venv_paths(active_python=fake_python)
    assert str(lib_dir) in paths

def test_check_sys_path_alignment():
    assert find_engine.check_sys_path_alignment("dummy") is None

def test_scan_for_module_shadowing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Create shadowing file
    (tmp_path / "sys.py").touch()
    
    # Mock other phases to return nothing
    monkeypatch.setattr(find_engine, "get_current_venv_paths", lambda x: [])
    monkeypatch.setattr(find_engine, "get_global_paths", lambda: [])
    
    results = find_engine.scan_for_module("sys")
    assert len(results) == 1
    assert "Shadowing" in results[0]["environment"]
    assert results[0]["warning"] is not None

def test_scan_for_module_venv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Setup fake venv
    venv_site = tmp_path / "venv" / "lib" / "python3.12" / "site-packages"
    venv_site.mkdir(parents=True)
    (venv_site / "requests").mkdir()
    
    monkeypatch.setattr(find_engine, "get_current_venv_paths", lambda x: [str(venv_site)])
    monkeypatch.setattr(find_engine, "get_global_paths", lambda: [])
    
    results = find_engine.scan_for_module("requests", active_python="fake")
    assert len(results) == 1
    assert results[0]["environment"] == "Active Virtual Environment"
    assert results[0]["warning"] is None

def test_scan_for_module_global(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Setup fake global path
    global_site = tmp_path / "global" / "site-packages"
    global_site.mkdir(parents=True)
    (global_site / "numpy").mkdir()
    
    # Setup active venv to trigger the warning message in Phase 3
    venv_site = tmp_path / "venv" / "site-packages"
    
    monkeypatch.setattr(find_engine, "get_current_venv_paths", lambda x: [str(venv_site)])
    monkeypatch.setattr(find_engine, "get_global_paths", lambda: [str(global_site)])
    
    # Mock engine categorize_path
    from envguard import engine
    monkeypatch.setattr(engine, "categorize_path", lambda x: "mocked_global_env")
    
    results = find_engine.scan_for_module("numpy", active_python="fake", deep=True)
    assert len(results) == 1
    assert results[0]["environment"] == "mocked_global_env"
    assert "not be available in your isolated venv" in results[0]["warning"]

def test_analyze_package_content(tmp_path):
    # Test Empty Directory
    empty_dir = tmp_path / "empty_pkg"
    empty_dir.mkdir()
    assert find_engine.analyze_package_content(str(empty_dir)) == "Pure Python (Native)"

    # Test Pure Python (Native) Directory
    py_dir = tmp_path / "py_pkg"
    py_dir.mkdir()
    with open(py_dir / "main.py", "w") as f:
        f.write("def hello():\n    pass")
    (py_dir / "__init__.py").touch()
    assert find_engine.analyze_package_content(str(py_dir)) == "Pure Python (Native)"

    # Test Pure Python (System Wrapper) Directory
    wrapper_dir = tmp_path / "wrapper_pkg"
    wrapper_dir.mkdir()
    with open(wrapper_dir / "main.py", "w") as f:
        f.write("import os\nimport subprocess\nsubprocess.run(['ls'])")
    (wrapper_dir / "__init__.py").touch()
    assert find_engine.analyze_package_content(str(wrapper_dir)) == "Pure Python (System Wrapper)"

    # Test C-Extension Directory (.so)
    so_dir = tmp_path / "so_pkg"
    so_dir.mkdir()
    (so_dir / "main.py").touch()
    (so_dir / "core.cpython-312-darwin.so").touch()
    assert find_engine.analyze_package_content(str(so_dir)) == "C-Extension / Bundled Binary"

    # Test C-Extension Directory (.dylib)
    dylib_dir = tmp_path / "dylib_pkg"
    dylib_dir.mkdir()
    (dylib_dir / "libengine.dylib").touch()
    assert find_engine.analyze_package_content(str(dylib_dir)) == "C-Extension / Bundled Binary"

    # Test C-Extension Directory (.pyd)
    pyd_dir = tmp_path / "pyd_pkg"
    pyd_dir.mkdir()
    (pyd_dir / "fast.pyd").touch()
    assert find_engine.analyze_package_content(str(pyd_dir)) == "C-Extension / Bundled Binary"
