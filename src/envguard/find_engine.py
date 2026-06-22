import os
import sys
import fnmatch
from typing import List, Dict, Optional
from envguard import engine, logger
from envguard.resolver import resolve_module_name

def get_current_venv_paths(active_python: str = None) -> List[str]:
    """Get the site-packages paths of the currently active virtual environment."""
    paths = []
    py_path = active_python or sys.executable
    if engine.detect_venv(py_path):
        env_dir = os.path.dirname(os.path.dirname(os.path.abspath(py_path)))
        lib_dir = os.path.join(env_dir, "lib")
        if os.path.isdir(lib_dir):
            for py_dir in os.listdir(lib_dir):
                if py_dir.startswith("python"):
                    site_pkg = os.path.join(lib_dir, py_dir, "site-packages")
                    if os.path.isdir(site_pkg):
                        paths.append(site_pkg)
    logger.debug(f"Extracted active venv site-packages: {paths}")
    return paths

def get_global_paths() -> List[str]:
    """Get the site-packages paths defined as global in rules.json."""
    paths = []
    rules = engine.load_rules()
    for env in rules.get("environments", []):
        if env.get("type") in ["system_global", "user_global"]:
            for pattern in env.get("path_patterns", []):
                expanded = os.path.expanduser(pattern)
                base = expanded.split("*")[0]
                if os.path.isdir(base):
                    # Glob it if needed, or simply append base if it's a prefix
                    pass # Simplified for Phase 2: let's scan actual paths
                    # For a robust scan, we should use glob. Here we just return the expanded prefixes.
                paths.append(expanded)
    logger.debug(f"Loaded {len(paths)} global base paths from rules.json")
    return paths

def check_sys_path_alignment(module_path: str) -> Optional[str]:
    """
    Check if the found module path aligns with sys.path priorities.
    Returns a warning string if there is a mismatch.
    """
    # Simple check: if module is found globally but sys.path prioritize a local venv first
    # For Phase 2, we just return a stub warning if it's outside the active venv but active venv exists.
    return None

def detect_shadowing(module_name: str, cwd: str) -> Optional[tuple[str, str]]:
    """Detect if there is a local file that shadows the module. Returns (warning_msg, actual_path)."""
    local_file = os.path.join(cwd, f"{module_name}.py")
    if os.path.isfile(local_file):
        return (f"[WARNING] Local file '{local_file}' is shadowing the package '{module_name}'!", local_file)
    
    local_dir = os.path.join(cwd, module_name)
    if os.path.isdir(local_dir) and os.path.isfile(os.path.join(local_dir, "__init__.py")):
        return (f"[WARNING] Local directory '{local_dir}' is shadowing the package '{module_name}'!", local_dir)
        
    return None

def analyze_package_content(package_path: str) -> str:
    """Analyze if the package is pure python or contains C-extensions."""
    if not os.path.isdir(package_path):
        # Could be a single .py file or shadowing file
        return "Pure Python (Native)"
        
    for root, _, files in os.walk(package_path):
        for f in files:
            if f.endswith(('.so', '.dylib', '.pyd')):
                return "C-Extension / Bundled Binary"
    
    # Check for System Wrapper signatures
    files_checked = 0
    max_files = 100
    keywords = [b'import subprocess', b'from subprocess import', b'os.system(', b'os.popen(']
    
    for root, _, files in os.walk(package_path):
        for f in files:
            if f.endswith('.py'):
                files_checked += 1
                try:
                    with open(os.path.join(root, f), 'rb') as f_obj:
                        content = f_obj.read()
                        if any(kw in content for kw in keywords):
                            return "Pure Python (System Wrapper)"
                except Exception:
                    pass
                if files_checked >= max_files:
                    break
        if files_checked >= max_files:
            break

    return "Pure Python (Native)"

def scan_for_module(module_name: str, deep: bool = False, active_python: str = None) -> List[Dict]:
    """
    Scan for the module using a 3-tier radius.
    """
    results = []
    cwd = os.getcwd()
    
    # 1. Check local shadowing
    print(f"🔍 [Phase 1] Scanning local workspace for '{module_name}' shadowing...")
    shadow_result = detect_shadowing(module_name, cwd)
    if shadow_result:
        shadow_warning, shadow_path = shadow_result
        logger.debug(f"[Step 1] Shadowing warning triggered: {shadow_warning}")
        results.append({
            "path": shadow_path,
            "environment": "Local Workspace (Shadowing!)",
            "package_name": module_name,
            "package_type": analyze_package_content(shadow_path),
            "warning": shadow_warning
        })
        
    # Translate module name to package name
    search_paths = get_current_venv_paths(active_python)
    pkg_name = resolve_module_name(module_name, search_paths)
    
    # 2. Check active venv
    if search_paths:
        print(f"🔍 [Phase 2] Scanning active virtual environment...")
    else:
        print(f"🔍 [Phase 2] No active virtual environment detected, skipping...")
        logger.debug("[Step 2] No active venv paths found")
        
    for sp in search_paths:
        mod_path = os.path.join(sp, module_name)
        pkg_path = os.path.join(sp, pkg_name)
        if os.path.exists(mod_path) or os.path.exists(pkg_path):
            found_path = mod_path if os.path.exists(mod_path) else pkg_path
            logger.debug(f"[Step 2] Found module/package in active venv: {found_path}")
            results.append({
                "path": found_path,
                "environment": "Active Virtual Environment",
                "package_name": pkg_name,
                "package_type": analyze_package_content(found_path),
                "warning": None
            })
            
    # 3. Check global environments (if deep scan is enabled, or if not found yet)
    if deep or not results:
        scan_reason = "(Deep scan enabled)" if deep else "(Not found in Phase 1 & 2)"
        print(f"🔍 [Phase 3] Scanning global environments {scan_reason}...")
        global_paths = get_global_paths()
        import glob
        logger.debug(f"[Step 3] Preparing to scan {len(global_paths)} global patterns")
        for pattern in global_paths:
            logger.debug(f"[Step 3] Evaluating pattern: {pattern}")
            expanded_dirs = glob.glob(pattern)
            logger.debug(f"[Step 3] Glob expansion found {len(expanded_dirs)} directories for pattern {pattern}")
            for sp in expanded_dirs:
                mod_path = os.path.join(sp, module_name)
                pkg_path = os.path.join(sp, pkg_name)
                if os.path.exists(mod_path) or os.path.exists(pkg_path):
                    cat = engine.categorize_path(sp)
                    found_path = mod_path if os.path.exists(mod_path) else pkg_path
                    logger.debug(f"[Step 3] Found in global environment: {found_path} (Categorized as: {cat})")
                    results.append({
                        "path": found_path,
                        "environment": cat,
                        "package_name": pkg_name,
                        "package_type": analyze_package_content(found_path),
                        "warning": "This package is installed globally. It might not be available in your isolated venv." if search_paths else None
                    })
                    
    return results
