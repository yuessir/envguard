import os
import subprocess
import json
from dataclasses import dataclass
from envguard import engine
from envguard.logger import debug

class GhostEnvironmentConflictError(Exception):
    pass

@dataclass
class EnvContext:
    prefix: str
    version_str: str
    is_venv: bool

def evaluate_security_status(pkg_path: str, context: EnvContext) -> str:
    """
    Pure function to determine the security status of a package path based on the environment context.
    Uses Guard Clauses for simplicity and clarity.
    """
    # Guard 1: Not in prefix -> LEAK (External pollution)
    if not pkg_path.startswith(context.prefix):
        return "LEAK"
    
    # Guard 2: Inside prefix, but under a mismatched python version directory -> CORRUPTED or LEAK
    if "/lib/python" in pkg_path and context.version_str not in pkg_path:
        if context.is_venv:
            return "CORRUPTED"
        else:
            # If it's a global environment, a mismatched version is considered a leak
            return "LEAK"
    
    # Guard 3: Everything matches -> SAFE
    return "SAFE"

def evaluate_wrapper_status(wrapper_info: dict, context: EnvContext) -> str:
    """
    Evaluates if an executable wrapper (like pip or jupyter) in the bin/ directory
    has a corrupted shebang pointing outside of the expected environment.
    """
    shebang_path = wrapper_info.get("shebang_path", "")
    if not shebang_path:
        return "SAFE"
        
    # If the shebang uses 'python' directly (e.g. via /usr/bin/env), it relies on $PATH.
    if shebang_path == "python" or shebang_path.startswith("python3"):
        return "SAFE"
        
    # Resolve the absolute path of the shebang executable
    if os.path.isabs(shebang_path):
        # FAST PATH: If the shebang literal string already points inside the prefix, it's safe.
        # This prevents false positives in venvs where .venv/bin/python is a symlink to the global python.
        if shebang_path.startswith(context.prefix):
            return "SAFE"
            
        try:
            real_shebang = os.path.realpath(shebang_path)
            # If the shebang's real path is outside the context prefix, it's corrupted.
            if not real_shebang.startswith(context.prefix):
                return "CORRUPTED_WRAPPER"
        except Exception:
            pass
            
    return "SAFE"

def find_target_python():
    """
    Finds the python executable and prefix to audit.
    Implements f-1 to f-4.
    """
    virtual_env = os.environ.get("VIRTUAL_ENV")
    debug(f"[Audit] VIRTUAL_ENV from environ: {virtual_env}")
    
    # Upward traversal
    cwd = os.getcwd()
    upward_venv = None
    for _ in range(4): # Check current dir and 3 parents
        potential_venv = os.path.join(cwd, ".venv")
        if os.path.exists(os.path.join(potential_venv, "pyvenv.cfg")):
            upward_venv = potential_venv
            break
            
        potential_venv2 = os.path.join(cwd, "venv")
        if os.path.exists(os.path.join(potential_venv2, "pyvenv.cfg")):
            upward_venv = potential_venv2
            break
            
        parent = os.path.dirname(cwd)
        if parent == cwd:
            break
        cwd = parent

    debug(f"[Audit] Upward venv traversal found: {upward_venv}")

    # f-2: Ghost Environment Conflict
    if virtual_env and upward_venv and os.path.realpath(virtual_env) != os.path.realpath(upward_venv):
        raise GhostEnvironmentConflictError(
            f"🚨 [EnvGuard Conflict] Your activated virtualenv ({virtual_env}) does not match the workspace virtualenv ({upward_venv})! "
            "You may have forgotten to deactivate the old environment. Please switch to the correct environment before auditing."
        )

    # f-1 & f-3
    target_prefix = virtual_env or upward_venv
    
    if target_prefix:
        python_exe = os.path.join(target_prefix, "bin", "python")
        if not os.path.exists(python_exe):
            python_exe = os.path.join(target_prefix, "bin", "python3")
        debug(f"[Audit] Target python resolved to {python_exe} via prefix {target_prefix}")
        return python_exe, target_prefix
        
    # f-4 Fallback
    fallback_python = engine.get_active_python()
    debug(f"[Audit] No venv found, falling back to active python: {fallback_python}")
    return fallback_python, None

def run_audit_probe(python_exe: str, scan_wrappers: bool = False):
    """
    Runs the audit probe using subprocess to get package distributions, sys.prefix,
    and detects GHOST dependencies (no metadata).
    """
    from envguard.engine import load_rules
    rules = load_rules()
    ghost_whitelist = rules.get("ghost_whitelist", ["sitecustomize", "usercustomize", "README", "__pycache__"])

    probe_path = os.path.join(os.path.dirname(__file__), "probes", "audit.py")
    
    config_payload = json.dumps({
        "ghost_whitelist": ghost_whitelist,
        "scan_wrappers": scan_wrappers
    })

    try:
        debug(f"[Audit] Running probe script '{probe_path}' with target python: {python_exe}")
        output = subprocess.check_output(
            [python_exe, probe_path], 
            input=config_payload,
            text=True, 
            stderr=subprocess.PIPE
        )
        debug(f"[Audit] Probe executed successfully. Parsing {len(output)} bytes of output.")
        return json.loads(output)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to run audit probe on {python_exe}: {e.stderr}")
