import sys
import argparse
from envguard.utils.colors import Colors
import json
from envguard import engine, hook, logger
from envguard.find_engine import scan_for_module

def print_warning(message: str):
    # ANSI yellow for warning
    print(f"{Colors.YELLOW}{message}{Colors.RESET}", file=sys.stderr)

def hook_exec(args):
    result = hook.check_alignment(args.executable, args.command, active_python=args.python, args=args.args)
    if result.get("abort"):
        print(f"{Colors.RED}{result.get('message', 'Execution aborted by EnvGuard.')}{Colors.RESET}", file=sys.stderr)
        sys.exit(1)
        
    if not result.get("aligned", True) and result.get("message"):
        print_warning(result["message"])

def find(args):
    active_py = args.python or engine.get_active_python()
    results = scan_for_module(args.module_name, deep=args.deep, active_python=active_py)
    if not results:
        print(f"{Colors.YELLOW}Could not find module '{args.module_name}' in the current scope.{Colors.RESET}")
    else:
        print(f"EnvGuard found '{args.module_name}' in the following locations:\n")
        for r in results:
            print(f"📍 Path: {r['path']}")
            print(f"   Environment: {r['environment']}")
            if r.get('package_type'):
                print(f"   📦 Type: {r['package_type']}")
            if r.get('package_name') and r['package_name'] != args.module_name:
                print(f"   Package: {r['package_name']}")
            if r.get('warning'):
                print(f"   {Colors.RED}{r['warning']}{Colors.RESET}")
            print("-" * 40)

def doctor(args):
    print(f"{Colors.BOLD}EnvGuard Doctor - Environment Health Report{Colors.RESET}")
    try:
        import shutil
        import os
        # Find the active python in the user's PATH, not the one running envguard
        current_python = engine.get_active_python()
        env_data = engine.analyze_executable(current_python)
        
        if env_data['original_path'] != env_data['real_path']:
            print(f"Current Python (Alias): {Colors.YELLOW}{env_data['original_path']}{Colors.RESET}")
            print(f"Current Python (Real):  {Colors.GREEN}{env_data['real_path']}{Colors.RESET}")
        else:
            print(f"Current Python: {Colors.GREEN}{env_data['real_path']}{Colors.RESET}")
        print(f"Is Virtual Env: {env_data['is_venv']}")
        print(f"Category:       {env_data['category']}")
        
        try:
            import subprocess
            import json
            code = "import sys, sysconfig, json; print(json.dumps({'version': sys.version.split()[0], 'prefix': sys.prefix, 'base_prefix': getattr(sys, 'base_prefix', sys.prefix), 'site_packages': sysconfig.get_path('purelib')}))"
            result = subprocess.run([current_python, "-c", code], capture_output=True, text=True)
            if result.returncode == 0:
                details = json.loads(result.stdout.strip())
                print(f"Version:        {details['version']}")
                print(f"Prefix:         {details['prefix']}")
                if details['prefix'] != details['base_prefix']:
                    print(f"Base Prefix:    {details['base_prefix']}")
                print(f"Site-Packages:  {details['site_packages']}")
        except Exception:
            pass
        
        print("\nChecking common tools...")
        tools_dict = engine.get_managed_tools()
        tools_to_check = []
        for cat in ["installer_tools", "execution_tools"]:
            if cat in tools_dict:
                tools_to_check.extend(tools_dict[cat])
        tools_to_check = list(dict.fromkeys(tools_to_check)) # remove duplicates
        
        home = os.path.expanduser("~")
        config_path = os.path.join(home, ".envguard", "config.json")
        cache_path = os.path.join(home, ".envguard", "tools.cache")
        if not os.path.exists(cache_path):
            print(f"{Colors.YELLOW}[HINT] 💡 EnvGuard shell hooks are not fully initialized. Run 'envguard init' to enable active protection.{Colors.RESET}\n")
        elif os.path.exists(config_path) and os.path.getmtime(config_path) > os.path.getmtime(cache_path):
            print(f"{Colors.YELLOW}[HINT] 💡 config.json has been modified. Run 'envguard init' and restart your terminal to apply changes.{Colors.RESET}\n")
            
        for tool in tools_to_check:
            tool_path = shutil.which(tool)
            if tool_path:
                res = hook.check_alignment(tool_path, tool, active_python=current_python)
                status = f"{Colors.GREEN}ALIGNED{Colors.RESET}" if res.get("aligned") else f"{Colors.RED}MISALIGNED{Colors.RESET}"
                category_label = res.get("tool_category", "unknown")
                print(f"- {tool} ({category_label}): {tool_path} [{status}]")
                if not res.get("aligned"):
                    print_warning(f"  -> {res.get('message').replace(chr(10), chr(10)+'  -> ')}")
            else:
                print(f"- {tool}: Not installed in PATH")
    except Exception as e:
        print_warning(f"Doctor encountered an error: {e}")

def audit(args):
    from envguard import audit_engine
    
    print(f"{Colors.BLUE}🛡️ EnvGuard Isolation Audit in Progress...{Colors.RESET}")
    print("=" * 60)
    
    try:
        target_python, target_prefix = audit_engine.find_target_python()
    except audit_engine.GhostEnvironmentConflictError as e:
        print(f"{Colors.RED}{e}{Colors.RESET}", file=sys.stderr)
        sys.exit(1)
        
    try:
        data = audit_engine.run_audit_probe(target_python)
    except Exception as e:
        print(f"{Colors.RED}Probe execution failed: {e}{Colors.RESET}", file=sys.stderr)
        sys.exit(1)
        
    context = audit_engine.EnvContext(
        prefix=data["prefix"], 
        version_str=data["version_str"],
        is_venv=data.get("is_venv", False)
    )
    
    # Analyze
    safe_pkgs = []
    leak_pkgs = []
    corrupted_pkgs = []
    
    for pkg in data["packages"]:
        status = audit_engine.evaluate_security_status(pkg["path"], context)
        # Get source if not safe
        source = ""
        if status != "SAFE":
            source = engine.categorize_path(pkg["path"])
        
        pkg_data = {
            "name": pkg["name"],
            "version": pkg["version"],
            "path": pkg["path"],
            "source": source
        }
        
        if status == "SAFE":
            safe_pkgs.append(pkg_data)
        elif status == "LEAK":
            leak_pkgs.append(pkg_data)
        elif status == "CORRUPTED":
            corrupted_pkgs.append(pkg_data)
            
    ghost_pkgs = data.get("ghosts", [])
    
    # Sort lists alphabetically by package name (case-insensitive)
    safe_pkgs.sort(key=lambda x: x["name"].lower())
    leak_pkgs.sort(key=lambda x: x["name"].lower())
    corrupted_pkgs.sort(key=lambda x: x["name"].lower())
    ghost_pkgs.sort(key=lambda x: x["name"].lower())
            
    is_safe_overall = len(leak_pkgs) == 0 and len(corrupted_pkgs) == 0 and len(ghost_pkgs) == 0
    
    if args.format == "table":
        all_pkgs = safe_pkgs + leak_pkgs + corrupted_pkgs + ghost_pkgs
        max_pkg = max([len(p['name']) for p in all_pkgs] + [7]) if all_pkgs else 7
        max_ver = max([len(str(p['version'])) for p in all_pkgs] + [7]) if all_pkgs else 7
        max_path = max([len(p['path']) for p in all_pkgs] + [9]) if all_pkgs else 9
        
        header_len = 13 + max_pkg + max_ver + max_path + 20 + 4
        print(f"{'STATUS':<13} {str('PACKAGE').ljust(max_pkg)} {str('VERSION').ljust(max_ver)} {str('REAL PATH').ljust(max_path)} SOURCE")
        print("─" * min(header_len, 120))
        
        for p in safe_pkgs:
            print(f"{Colors.GREEN}{'[SAFE]':<13}{Colors.RESET} {p['name'].ljust(max_pkg)} {str(p['version']).ljust(max_ver)} {p['path'].ljust(max_path)} Virtual Env")
        for p in leak_pkgs:
            print(f"{Colors.RED}{'[LEAK]':<13}{Colors.RESET} {p['name'].ljust(max_pkg)} {str(p['version']).ljust(max_ver)} {p['path'].ljust(max_path)} {p['source']}")
        for p in corrupted_pkgs:
            print(f"{Colors.RED}{'[CORRUPTED]':<13}{Colors.RESET} {p['name'].ljust(max_pkg)} {str(p['version']).ljust(max_ver)} {p['path'].ljust(max_path)} {p['source']}")
        for p in ghost_pkgs:
            print(f"{Colors.PURPLE}{'[GHOST]':<13}{Colors.RESET} {p['name'].ljust(max_pkg)} {str(p['version']).ljust(max_ver)} {p['path'].ljust(max_path)} No Metadata")
            
        print("─" * min(header_len, 120))
        if is_safe_overall:
            print("✅ Audit Conclusion: All packages are safely isolated.")
        else:
            total_issues = len(leak_pkgs) + len(corrupted_pkgs) + len(ghost_pkgs)
            print(f"🔥 Audit Conclusion: Found {total_issues} environment inconsistencies. This may cause project recreation to fail on other machines!")
    else:
        # Categorized view
        print(f"[Current Environment]: {target_prefix or target_python} ({data['version_str']})")
        if is_safe_overall:
            print(f"[Isolation Status]: {Colors.GREEN}✅ Strictly Isolated{Colors.RESET}")
        else:
            print(f"[Isolation Status]: {Colors.YELLOW}⚠️ Leaked Environment Detected{Colors.RESET}")
        print("=" * 60)
        print()
        
        print(f"{Colors.GREEN}✅ Safe Packages (Strictly Isolated){Colors.RESET}")
        print("-" * 60)
        print(f"[...Total {len(safe_pkgs)} safely isolated packages...]")
        print()
        
        if leak_pkgs:
            print(f"{Colors.YELLOW}🚨 Leaked Dependencies{Colors.RESET}")
            print("-" * 60)
            for p in leak_pkgs:
                print(f"  📦 {p['name']} ({p['version']})")
                print(f"     ├── Real Path: {p['path']}")
                print(f"     └── Source: {p['source']}")
                print()
                
        if ghost_pkgs:
            print(f"{Colors.PURPLE}👻 Phantom Modules (No Metadata){Colors.RESET}")
            print("-" * 60)
            for p in ghost_pkgs:
                print(f"  👻 {p['name']} ({p['version']})")
                print(f"     ├── Real Path: {p['path']}")
                print(f"     └── Warning: This module has no PyPI metadata. It is likely a system-level installation (MacPorts/APT) and will be missed by pip freeze!")
                print()
                
        if corrupted_pkgs:
            print(f"{Colors.RED}💥 Corrupted Packages (Internals Mismatch){Colors.RESET}")
            print("-" * 60)
            for p in corrupted_pkgs:
                print(f"  📦 {p['name']} ({p['version']})")
                print(f"     ├── Real Path: {p['path']}")
                print(f"     └── Diagnosis: 💥 Version mismatch! Current environment is {data['version_str']}, but legacy packages were found. Consider rebuilding the virtualenv.")
                print()

    # Common Warnings Section (Always printed at the very end if --verbose is True)
    warnings = data.get("warnings", [])
    if getattr(args, "verbose", False) and warnings:
        print()
        print(f"{Colors.YELLOW}⚠️  Probe Warnings{Colors.RESET}")
        print("-" * 60)
        for w in warnings:
            print(f"  - {w}")
        print()

def init(args):
    import os
    import shutil
    import sysconfig
    
    print(f"{Colors.BOLD}Initializing EnvGuard Shell Hooks...{Colors.RESET}")
    
    # Locate package shell scripts
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    shell_dir = os.path.join(pkg_dir, "shell")
    
    # Create ~/.envguard
    home = os.path.expanduser("~")
    envguard_home = os.path.join(home, ".envguard")
    os.makedirs(envguard_home, exist_ok=True)
    
    config_path = os.path.join(envguard_home, "config.json")
    cache_path = os.path.join(envguard_home, "tools.cache")
    
    # 1. Generate config.json (idempotent)
    if not os.path.exists(config_path):
        default_tools = engine.get_managed_tools()
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"managed_tools": default_tools}, f, indent=4)
        print(f"Created default configuration at: {config_path}")
        
    # 2. Generate tools.cache (always overwrite)
    tools = engine.get_managed_tools()
    all_tools = set()
    for cat, tool_list in tools.items():
        all_tools.update(tool_list)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(" ".join(sorted(list(all_tools))))
    print(f"Generated tools cache at: {cache_path}")
    
    # Copy scripts
    plugin_zsh = os.path.join(shell_dir, "envguard.plugin.zsh")
    plugin_bash = os.path.join(shell_dir, "envguard.bash")
    if os.path.exists(plugin_zsh):
        shutil.copy(plugin_zsh, envguard_home)
    if os.path.exists(plugin_bash):
        shutil.copy(plugin_bash, envguard_home)
        
    # Detect shell
    shell_path = os.environ.get("SHELL", "")
    rc_file = None
    source_script = ""
    if "zsh" in shell_path:
        rc_file = os.path.join(home, ".zshrc")
        source_script = "envguard.plugin.zsh"
    elif "bash" in shell_path:
        rc_file = os.path.join(home, ".bashrc")
        source_script = "envguard.bash"
    else:
        print_warning(f"Unsupported shell: {shell_path}. Please manually source the scripts in {envguard_home}")
        return

    # Check PATH for envguard
    envguard_executable = shutil.which("envguard")
    if envguard_executable:
        envguard_bin_dir = os.path.dirname(envguard_executable)
    else:
        # Fallback if not in path, use sys.argv[0] if it's absolute, else use sysconfig
        if os.path.isabs(sys.argv[0]) and os.path.exists(sys.argv[0]):
            envguard_bin_dir = os.path.dirname(sys.argv[0])
        else:
            envguard_bin_dir = sysconfig.get_path("scripts")
        
    path_export = ""
    current_path = os.environ.get("PATH", "")
    if envguard_bin_dir not in current_path.split(os.pathsep):
        path_export = f'export PATH="{envguard_bin_dir}:$PATH"\n'
        print(f"{Colors.YELLOW}[EnvGuard] Detected that {envguard_bin_dir} is not in your PATH. Adding it automatically.{Colors.RESET}")
    
    # Generate block
    block_start = f"# >>> envguard initialize >>>"
    block_end = f"# <<< envguard initialize <<<"
    block = f"""
{block_start}
{path_export}if [ -f ~/.envguard/{source_script} ]; then
    source ~/.envguard/{source_script}
fi
{block_end}
"""

    # Print installation info
    envguard_exe = os.path.join(envguard_bin_dir, "envguard")
    if os.path.exists(envguard_exe):
        env_data = engine.analyze_executable(envguard_exe)
        print(f"EnvGuard installed at: {Colors.BLUE}{env_data['real_path']}{Colors.RESET}")
        print(f"Installation Category: {Colors.BLUE}{env_data['category']}{Colors.RESET}")

    if os.path.exists(rc_file):
        with open(rc_file, "r") as f:
            content = f.read()
        if block_start in content:
            print(f"EnvGuard initialization block already exists in {rc_file}.")
            return
            
    with open(rc_file, "a") as f:
        f.write(f"\n{block}")
        
    print(f"{Colors.GREEN}Successfully injected EnvGuard initialization into {rc_file}.{Colors.RESET}")
    print(f"Please restart your terminal or run: {Colors.BOLD}source {rc_file}{Colors.RESET}")

def main():
    parser = argparse.ArgumentParser(description="EnvGuard - Python Environment Conflict Diagnostics")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    
    # Hook exec
    hook_parser = subparsers.add_parser("hook-exec", help="Internal hook called by shell wrappers")
    hook_parser.add_argument("command", help="Command name")
    hook_parser.add_argument("executable", help="Resolved path to the command")
    hook_parser.add_argument("--python", help="Path to the active python executable", default=None)
    hook_parser.set_defaults(func=hook_exec)
    
    # Doctor
    doctor_parser = subparsers.add_parser("doctor", help="Run active diagnostics on current environment")
    doctor_parser.set_defaults(func=doctor)
    
    # Init
    init_parser = subparsers.add_parser("init", help="Initialize shell hooks and inject into rc file")
    init_parser.set_defaults(func=init)
    
    parser_find = subparsers.add_parser(
        "find", 
        help="Find a Python package or module across environments.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Package Types Explained:
  📦 Pure Python (Native):         100% Python code. No system commands or C-extensions.
  📦 Pure Python (System Wrapper): Python code that invokes external OS commands (e.g., tesseract).
                                   If this fails, check your OS $PATH or package manager (brew/port).
  📦 C-Extension / Bundled Binary: Contains compiled C/C++ engine files (.so/.dylib/.pyd) inside it.
"""
    )
    parser_find.add_argument("module_name", help="The name of the module to find (e.g., cv2, django)")
    parser_find.add_argument("--deep", action="store_true", help="Perform a deep scan across all known global environments")
    parser_find.add_argument("--python", help="Path to the active python interpreter", default=None)
    parser_find.set_defaults(func=find)
    
    audit_parser = subparsers.add_parser("audit", help="Check runtime environment isolation status")
    audit_parser.add_argument("--format", choices=["categorized", "table"], default="categorized", help="Output format")
    audit_parser.add_argument("--verbose", action="store_true", help="Print underlying probe warnings")
    audit_parser.set_defaults(func=audit)
    
    args, unknown = parser.parse_known_args()
    if args.subcommand == "hook-exec":
        args.args = unknown
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n{Colors.RED}Interrupted by user{Colors.RESET}", file=sys.stderr)
        sys.exit(130)

if __name__ == "__main__":
    main()
