import os
import json
import fnmatch
from envguard import logger

def get_active_python() -> str:
    """
    Get the truly active python path from the user's $PATH, falling back to sys.executable.
    This prevents EnvGuard from mistaking its own installation environment as the user's active environment.
    """
    import shutil
    import sys
    return shutil.which("python3") or shutil.which("python") or sys.executable

def load_rules():
    """Load the central rules.json file."""
    rules_path = os.path.join(os.path.dirname(__file__), "data", "rules.json")
    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f"Failed to load rules.json: {e}")
        return {"environments": [], "managed_tools": {}}

def get_managed_tools() -> dict:
    """
    Get the configured managed tools.
    Prioritizes ~/.envguard/config.json, falls back to rules.json.
    """
    default_tools = {
        "installer_tools": ["pip", "pip3"],
        "execution_tools": ["pyinstaller", "pytest", "celery", "uvicorn"],
        "bypass_tools": ["uv", "uvx"]
    }
    
    # 1. Try reading user config
    try:
        home_dir = os.path.expanduser("~")
        config_path = os.path.join(home_dir, ".envguard", "config.json")
        if os.path.isfile(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                if "managed_tools" in config_data:
                    return config_data["managed_tools"]
    except Exception as e:
        logger.debug(f"Failed to load user config.json: {e}")
        
    # 2. Fallback to rules.json
    rules = load_rules()
    if "managed_tools" in rules:
        return rules["managed_tools"]
        
    # 3. Ultimate fail-safe
    return default_tools

def resolve_real_path(executable_path: str) -> str:
    """Resolve symlinks or bash shims to find the real path of the executable."""
    try:
        # Check if it's a bash shim (like pyenv)
        if os.path.isfile(executable_path) and not os.path.islink(executable_path):
            try:
                with open(executable_path, 'rb') as f:
                    first_line = f.readline()
                    if b'bash' in first_line:
                        import subprocess
                        res = subprocess.run(["pyenv", "which", os.path.basename(executable_path)], capture_output=True, text=True)
                        if res.returncode == 0:
                            return res.stdout.strip()
            except Exception as e:
                pass
        
        real = os.path.realpath(executable_path)
        if real != executable_path:
            logger.debug(f"Resolved symlink: {executable_path} -> {real}")
        return real
    except Exception as e:
        logger.debug(f"Error resolving real path for {executable_path}: {e}")
        return executable_path

def detect_venv(executable_path: str) -> bool:
    """
    Detect if the given python executable is within a virtual environment.
    Phase 2: Strict PEP 405 Duck-typing. 
    Must have pyvenv.cfg and a corresponding lib/pythonX.X/site-packages directory.
    """
    try:
        bin_dir = os.path.dirname(executable_path)
        env_dir = os.path.dirname(bin_dir)
        pyvenv_cfg = os.path.join(env_dir, "pyvenv.cfg")
        conda_history = os.path.join(env_dir, "conda-meta", "history")
        
        is_pep405 = os.path.isfile(pyvenv_cfg)
        is_conda = os.path.isfile(conda_history)
        
        if not (is_pep405 or is_conda):
            # Check for Windows conda (python.exe in env_dir directly, so bin_dir IS env_dir)
            conda_history_win = os.path.join(bin_dir, "conda-meta", "history")
            if os.path.isfile(conda_history_win):
                is_conda = True
                env_dir = bin_dir
            else:
                return False
            
        # PEP 405 / Conda strictness: check if lib/python*/site-packages exists
        if is_pep405 or (is_conda and os.name != 'nt'):
            lib_dir = os.path.join(env_dir, "lib")
            if not os.path.isdir(lib_dir):
                return False
                
            for py_dir in os.listdir(lib_dir):
                if py_dir.startswith("python"):
                    site_packages = os.path.join(lib_dir, py_dir, "site-packages")
                    if os.path.isdir(site_packages):
                        return True
                        
            return False
        elif is_conda and os.name == 'nt':
            site_packages = os.path.join(env_dir, "Lib", "site-packages")
            if os.path.isdir(site_packages):
                return True
            return False
    except Exception as e:
        logger.debug(f"Error in detect_venv for {executable_path}: {e}")
        return False

def categorize_path(real_path: str) -> str:
    """Categorize the path based on rules.json patterns."""
    rules = load_rules()
    for env in rules.get("environments", []):
        for pattern in env.get("path_patterns", []):
            expanded = os.path.expanduser(pattern)
            
            # Direct match
            if fnmatch.fnmatch(real_path, expanded) or fnmatch.fnmatch(real_path, expanded + "/*"):
                return env.get("id")
            if "*" not in pattern and real_path.startswith(expanded):
                return env.get("id")
                
            # Base path match for bin/python binaries
            base_pattern = expanded.split("/lib/python")[0].split("/envs/")[0].split("/virtualenvs/")[0]
            if base_pattern != expanded:
                if fnmatch.fnmatch(real_path, base_pattern + "/*"):
                    return env.get("id")
            
            # Special case for conda fallback
            if env.get("id") == "conda_workspace_env" and "conda" in real_path.lower():
                return "conda_workspace_env"
                
    # macOS system default hardcoded fallback
    if real_path.startswith("/Library/Developer/CommandLineTools") or real_path.startswith("/usr/bin/"):
        return "macos_system_env"
        
    return "unknown"

def analyze_executable(executable_path: str, _override_usr_local_bin: str = None) -> dict:
    """
    Analyze the executable and return its environment characteristics.
    """
    real_path = resolve_real_path(executable_path)
    is_venv = detect_venv(executable_path)
    
    usr_local_bin = _override_usr_local_bin or "/usr/local/bin"
    
    # If it is a venv, category is venv
    venv_path = None
    if is_venv:
        category = "venv"
        venv_path = os.path.dirname(os.path.dirname(os.path.abspath(executable_path)))
    else:
        # Check source compiled: in /usr/local/bin and not a symlink
        # meaning real_path is inside /usr/local/bin (or the overridden one)
        is_symlink = os.path.islink(executable_path)
        
        # We need to be careful with override in tests
        in_usr_local = executable_path.startswith(usr_local_bin)
        
        if in_usr_local and not is_symlink:
            category = "source_compiled"
        else:
            category = categorize_path(real_path)
            
    logger.debug(f"Categorized '{executable_path}' as: {category} (is_venv: {is_venv})")
    
    return {
        "original_path": executable_path,
        "real_path": real_path,
        "is_venv": is_venv,
        "category": category,
        "venv_path": venv_path
    }
