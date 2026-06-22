from envguard.resolver import resolve_module_name

def test_resolve_module_name_static_mapping():
    assert resolve_module_name("cv2") == "opencv-python"
    assert resolve_module_name("bs4") == "beautifulsoup4"
    assert resolve_module_name("unknown_module") == "unknown_module"

def test_resolve_module_name_dynamic(tmp_path):
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    
    dist_info = site_packages / "requests-2.28.1.dist-info"
    dist_info.mkdir()
    
    top_level = dist_info / "top_level.txt"
    top_level.write_text("requests\n")
    
    assert resolve_module_name("requests", [str(site_packages)]) == "requests"

def test_resolve_module_name_dynamic_edge_cases(tmp_path):
    site_packages = tmp_path / "site-packages"
    site_packages.mkdir()
    
    # Non-existent search path should be skipped
    assert resolve_module_name("foo", ["/non/existent/path"]) == "foo"
    
    # Missing top_level.txt inside dist-info
    dist_info = site_packages / "fake-1.0.dist-info"
    dist_info.mkdir()
    assert resolve_module_name("fake", [str(site_packages)]) == "fake"
    
    # empty top_level.txt
    top_level = dist_info / "top_level.txt"
    top_level.touch()
    assert resolve_module_name("fake", [str(site_packages)]) == "fake"
