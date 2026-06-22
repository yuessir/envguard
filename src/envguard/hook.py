import sys
import os
import re
from envguard import engine, logger

def extract_python_version(file_path: str):
    """Extract python version from path string, shebang, or by executing it."""
    
    # 1. Try executing it directly if it is a python interpreter
    basename = os.path.basename(file_path)
    if basename.startswith("python"):
        try:
            import subprocess
            res = subprocess.run([file_path, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"], capture_output=True, text=True, timeout=1)
            if res.returncode == 0:
                version = res.stdout.strip()
                logger.debug(f"Extracted version v{version} by executing python: {file_path}")
                return version
        except Exception as e:
            logger.debug(f"Failed to execute python for version {file_path}: {e}")
            pass

    # 2. Extract from path string
    version_match = re.search(r'(3\.\d+)', file_path)
    if version_match:
        version = version_match.group(1)
        logger.debug(f"Extracted version v{version} from path string: {file_path}")
        return version
    
    # 3. Try reading shebang
    try:
        with open(file_path, 'r') as f:
            first_line = f.readline()
            if first_line.startswith('#!'):
                version_match = re.search(r'(3\.\d+)', first_line)
                if version_match:
                    version = version_match.group(1)
                    logger.debug(f"Extracted version v{version} from shebang in: {file_path}")
                    return version
    except Exception as e:
        logger.debug(f"Failed to read shebang for {file_path}: {e}")
        pass
        
    logger.debug(f"Could not extract Python version for: {file_path}")
    return None

def check_alignment(executable_path: str, command: str, active_python: str = None, args: list = None) -> dict:
    """
    Check if the executable aligns with the current python environment.
    If not, return a warning message.
    """
    try:
        # Use provided active python, or check PATH, or fallback to sys.executable
        if not active_python:
            active_python = engine.get_active_python()
            
        python_to_check = active_python
        current_env = engine.analyze_executable(python_to_check)
        tool_env = engine.analyze_executable(executable_path)
        
        logger.debug(f"Hook check: command='{command}', python='{python_to_check}', tool='{executable_path}'")
        args = args or []
        
        # Scenario 0: PEP 668 bypass attempt
        tools_dict = engine.get_managed_tools()
        installer_tools = tools_dict.get("installer_tools", [])
        bypass_tools = tools_dict.get("bypass_tools", [])
        execution_tools = tools_dict.get("execution_tools", [])
        
        if command in installer_tools and "install" in args and "--break-system-packages" in args:
            if not sys.stdout.isatty():
                return {
                    "aligned": False,
                    "abort": True,
                    "message": "[DANGER] Attempted to use --break-system-packages in a non-interactive environment (CI/CD).\nEnvGuard has blocked this to prevent breaking the system environment.",
                    "tool_category": tool_env.get("category", "unknown")
                }
            else:
                return {
                    "aligned": False,
                    "abort": False,
                    "message": "[WARNING] You are using --break-system-packages interactively.\nProceed with caution! This may break your OS Python installation.",
                    "tool_category": tool_env.get("category", "unknown")
                }
        
        # Scenario 1: User is in a venv, but the tool is global
        if current_env["is_venv"] and not tool_env["is_venv"]:
            if command in bypass_tools:
                # uv is intentionally a global tool that targets the active venv automatically.
                # We bypass the mismatch warning for global uv.
                pass
            elif command in installer_tools:
                return {
                    "aligned": False,
                    "message": f"[WARNING] You are in a virtual environment, but using a global {command}.\n"
                               f"Current Python: {current_env['real_path']}\n"
                               f"Tool Path: {tool_env['real_path']}\n"
                               f"This may install packages globally instead of in your venv.",
                    "tool_category": tool_env["category"]
                }
            elif command in execution_tools:
                return {
                    "aligned": False,
                    "message": f"[WARNING] You are in a virtual environment, but using a global {command}.\n"
                               f"Current Python: {current_env['real_path']}\n"
                               f"Tool Path: {tool_env['real_path']}\n"
                               f"This may lead to ModuleNotFoundError as the global tool cannot see venv packages.",
                    "tool_category": tool_env["category"]
                }
                
        if not current_env["is_venv"] and not tool_env["is_venv"]:
            logger.debug("Both environments are global. Performing version alignment check...")
            current_version = extract_python_version(current_env["real_path"])
            tool_version = extract_python_version(tool_env["real_path"])
            
            if current_version and tool_version and current_version != tool_version:
                tool_dir = os.path.dirname(tool_env['original_path'] if 'original_path' in tool_env else tool_env['real_path'])
                command_clean = command.replace('3', '') if command.startswith('pip') else command
                
                return {
                    "aligned": False,
                    "message": f"[WARNING] Global Python Version Mismatch!\n"
                               f"Active Python: {current_env['real_path']} (v{current_version})\n"
                               f"Tool Path: {tool_env['real_path']} (v{tool_version})\n"
                               f"Using this {command} will install/run against the wrong Python version.\n"
                               f"----------------------------------------------------------------------\n"
                               f"[HINT] 💡 Why did this happen?\n"
                               f"Your terminal found '{command}' in a directory that has higher priority in your $PATH:\n"
                               f"  -> {tool_dir}\n\n"
                               f"🛠️  How to fix it:\n"
                               f"1. Safe bypass: Run 'python -m {command_clean}' instead of just '{command}'.\n"
                               f"2. Permanent fix: Clean up your $PATH configuration (e.g., in ~/.zshrc) to ensure your v{current_version} bin folder appears before other versions.\n",
                    "tool_category": tool_env["category"]
                }

        # Future scenarios (like two different venvs) can be added here
        if current_env["is_venv"] and tool_env["is_venv"]:
            # Check if they belong to the same venv
            current_venv_path = current_env["venv_path"]
            tool_venv_path = tool_env["venv_path"]
            if current_venv_path != tool_venv_path:
                return {
                    "aligned": False,
                    "message": f"[WARNING] Environment mismatch!\n"
                               f"Active venv: {current_venv_path}\n"
                               f"Tool's venv: {tool_venv_path}",
                    "tool_category": tool_env["category"]
                }
                
        return {"aligned": True, "message": "", "tool_category": tool_env["category"]}
    except Exception as e:
        logger.debug(f"Hook encountered an error during check: {e}")
        # Silent Fail: If anything goes wrong, do not block the user.
        return {"aligned": True, "message": "", "error": str(e), "tool_category": "unknown"}

if __name__ == "__main__":
    import json
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", help="Path to the executable being run")
    parser.add_argument("command", help="The command name (e.g. pip, pyinstaller)")
    args = parser.parse_args()
    
    result = check_alignment(args.executable, args.command)
    print(json.dumps(result))
