# EnvGuard

[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

EnvGuard is a cross-environment CLI interceptor and path conflict diagnostic tool for Python.
It prevents common issues caused by misaligned paths between global tools, system environments, and virtual environments (`venv`).

## Core Features
- **Passive Guard:** Intercepts risky commands (like `pip install`, `pyinstaller`) if they are executed with a misaligned environment.
- **Proactive Diagnostics:** Provides an `envguard doctor` command to scan and report environment health.
- **Module Radar:** Provides `envguard find <module_name>` to locate python packages across Local, Virtual, and 10+ Global environment types (Conda, Pyenv, MacPorts, Homebrew, etc.).
- **Dynamic Package Analysis:** Automatically scans the physical contents and source code of Python packages to classify them as `Native`, `System Wrapper`, or `C-Extension` to eliminate the "where is the underlying executable?" confusion.
- **Isolation Audit:** Deep scans the environment to detect leaked dependencies, corrupted internals, and "Ghost Modules" (packages without metadata).
- **Smart Safety Nets:** Warns against `--break-system-packages` usage, instantly aborting in non-interactive CI/CD environments.

## Installation

```bash
# 1. Install via pip or uv
pip install envguard
# or
uv pip install envguard

# 2. Initialize shell hooks (Zsh/Bash)
envguard init

# 3. Restart your terminal or source your rc file
source ~/.zshrc
```

## Configuration (`~/.envguard/config.json`)

EnvGuard's protection is entirely **Configuration-Driven**. Upon running `envguard init`, a default configuration file is generated at `~/.envguard/config.json`. 

You can customize this JSON file to add any command-line tool you want EnvGuard to intercept and protect. It acts as a universal safety net, and works perfectly even for non-Python system tools (e.g., `brew`, `port`, `npm`).

```json
{
    "managed_tools": {
        "installer_tools": ["pip", "pip3", "port", "brew"],
        "execution_tools": ["pyinstaller", "pytest", "celery", "uvicorn"],
        "bypass_tools": ["uv", "uvx"]
    }
}
```

> [!IMPORTANT]
> **Zero-Latency Shell Hooks & Hot-Reloading**
> EnvGuard's shell hooks are designed for 0ms terminal startup overhead. After editing `config.json`, you **MUST run `envguard init` again** to compile your changes into a plaintext cache (`~/.envguard/tools.cache`).
> **Proactive Sync & Hot-Reload:** If you forget to sync, any `envguard` command will proactively display a smart hint. Once you run `envguard init`, EnvGuard will instantly **hot-reload** the new hooks into your current terminal—no need to open a new tab or restart your shell!

### Advanced Rules (`rules.json`)
EnvGuard relies on an internal `rules.json` file for advanced heuristics, such as defining `ghost_whitelist` (to ignore safe metadata-less modules like `sitecustomize` or `__pycache__`) and defining `blacklist_directories` for searching. You can customize this file inside the source code if you need to bypass specific ghost module false positives.

## Platform Support

EnvGuard's core logic is built on Unix/POSIX standards, ensuring excellent cross-platform stability:

- **macOS (Intel & Apple Silicon):** ✅ Fully Supported. Supports Zsh interception and is compatible with Homebrew (`/usr/local` or `/opt/homebrew`) and MacPorts.
- **Linux (Ubuntu, Debian, CentOS, etc.):** ✅ Fully Supported. Supports Bash/Zsh interception and accurately resolves `pyenv` shims.
- **Windows:** ⚠️ Partially Supported (WIP). Proactive diagnostic commands like `envguard doctor` and `envguard audit` run normally, but passive interception (Shell Hooks) for PowerShell / CMD is not yet supported. For a complete experience on Windows, using WSL2 is highly recommended.

## Usage & Examples
Once initialized, EnvGuard runs silently in the background. It will only interrupt you when it detects a critical environment misalignment.

### 1. Active Diagnostics (`envguard doctor`)
Run this anytime to see a deep analysis of your current Python environment and verify if your common tools (`pip`, `pytest`, etc.) are aligned.

```bash
envguard doctor
```
**Example Output:**
```text
EnvGuard Doctor - Environment Health Report
Current Python (Alias): /opt/local/bin/python3
Current Python (Real):  /opt/local/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
Is Virtual Env: False
Category:       macports
Version:        3.12.13
Prefix:         /opt/local/Library/Frameworks/Python.framework/Versions/3.12
Site-Packages:  /opt/local/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages

Checking common tools...
- pip (user_global): /Users/kevin/Library/Python/3.9/bin/pip [MISALIGNED]
- pytest (system): /usr/local/bin/pytest [ALIGNED]
```
*(EnvGuard explicitly separates your "Alias" from the "Real" binary path, so you are never fooled by symlinks again.)*

### 2. Passive Guard (Zero-Latency Interception)
If your `$PATH` is misconfigured and you accidentally run a tool that belongs to a different Python version (e.g., executing a 3.9 `pip` while your active Python is 3.12), EnvGuard instantly catches it:

```bash
$ pip install requests
[WARNING] Global Python Version Mismatch!
Active Python: /opt/local/bin/python3.12 (v3.12)
Tool Path: /Users/kevin/Library/Python/3.9/bin/pip (v3.9)
Using this pip will install/run against the wrong Python version.
----------------------------------------------------------------------
[HINT] 💡 Why did this happen?
Your terminal found 'pip' in a directory that has higher priority in your $PATH:
  -> /Users/kevin/Library/Python/3.9/bin

🛠️  How to fix it:
1. Safe bypass: Run 'python -m pip' instead of just 'pip'.
2. Permanent fix: Clean up your $PATH configuration (e.g., in ~/.zshrc) to ensure your v3.12 bin folder appears before other versions.
```

**Wrapper Integrity Check (Shebang Mismatch):**
In addition to checking the external Python environment, EnvGuard deeply inspects wrapper scripts. If you run a command (e.g., `jupyter`), and EnvGuard detects that the script's internal Shebang (`#!/path/to/python`) points to a different Python version than its folder path, it emits a structural inconsistency warning. This prevents scenarios where you run a command from Environment A but accidentally install packages into Environment B.

> [!NOTE]
> **Hook Bypass Limitations & Lifecycle**
> 1. **Bypass Limitations**: EnvGuard's dynamic Hooks are implemented using Zsh/Bash `function`s. Therefore, they **only intercept bare commands** (e.g., typing `jupyter`). If you use a relative or absolute path (e.g., `./jupyter` or `/bin/jupyter`), the Shell forces direct execution of the binary, bypassing the function entirely. In this case, the Hook will **not** trigger.
> 2. **Lifecycle**: EnvGuard binds hook functions when the terminal starts, based on the managed tools list (defaulting to `~/.envguard/tools.cache`). If you modify `rules.json` to add or remove tools, currently open terminals will not automatically know! You must run `envguard init` to hot-reload the current terminal so the interception net is rebuilt.


### 3. Module Radar (`envguard find`)
Have you ever seen a `ModuleNotFoundError` despite being sure you ran `pip install` earlier? EnvGuard provides a powerful 3-tier search engine to scan your Local Workspace, Active Virtual Environment, and all known System Global Environments (driven by `rules.json`).

> [!NOTE]
> **Python Module Name vs. OS Package Name**
> `envguard find` is designed to search for the **Python module name** (e.g., `numpy`), which is the exact name you type in your `import` statements. Do NOT search for OS package manager names (like `py312-numpy` or `python3-numpy`). EnvGuard directly scans the `site-packages` directories for the actual Python source code.

```bash
envguard find cv2
```
**Example Output:**
```text
🔍 [Phase 1] Scanning local workspace for 'cv2' shadowing...
🔍 [Phase 2] No active virtual environment detected, skipping...
🔍 [Phase 3] Scanning global environments (Not found in Phase 1 & 2)...
EnvGuard found 'cv2' in the following locations:

📍 Path: /opt/local/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/cv2
   Environment: macports_global_env
   📦 Type: C-Extension / Bundled Binary
   Package: opencv-python
```
*(Automatically resolves common import names like `cv2` -> `opencv-python` and classifies the physical structure of the package so you instantly know if it bundles a C-Engine or wraps an external OS command).*

**Package Types Explained:**
EnvGuard acts as an X-ray for your python packages, classifying them into three distinct types to help you troubleshoot "missing executable" or "missing engine" errors:
- `📦 Pure Python (Native)`: 100% Python code. No system commands or C-extensions. (e.g., `requests`, `pytest`)
- `📦 Pure Python (System Wrapper)`: Pure Python code that heavily invokes external OS commands. (e.g., `pytesseract`). **Diagnostic Hint:** If this package fails, check your OS `$PATH` or package manager (Brew/MacPorts) because the underlying engine is NOT installed in your Python environment.
- `📦 C-Extension / Bundled Binary`: Contains compiled C/C++ engine files (`.so`, `.dylib`, `.pyd`) packed inside it. (e.g., `cv2`, `numpy`). **Diagnostic Hint:** The engine is self-contained. You do not need to install external OS libraries.

### 4. Isolation Audit (`envguard audit`)
The `audit` command performs a deep scan of your target Python environment. It iterates through all installed packages, inspecting their physical files, metadata, and site-packages structure to evaluate their isolation integrity.

```bash
# Run a categorized audit report
envguard audit

# Run with table format
envguard audit --format table

# Deep scan for corrupted wrapper scripts (Shebang Mismatches)
envguard audit --scan-wrappers

# Run with verbose warnings (to see underlying permission/probe errors)
envguard audit --verbose
```

> [!TIP]
> **Why do we need static scanning with `--scan-wrappers`?**
> As mentioned above, dynamic Hooks cannot intercept commands executed with explicit paths (like `./jupyter`). This is where `--scan-wrappers` shines. It performs a comprehensive static check of all binary wrappers in your `bin/` directory, surfacing any **[BAD WRAPPER]** that points outside your active environment!

EnvGuard will classify each package into one of five states:
- `[SAFE]`: Properly installed and isolated.
- `[LEAK]`: Pulled from an unauthorized external environment (e.g., a virtualenv secretly loading global site-packages).
- `[CORRUPTED]`: Internal mismatch between python version and package contents (e.g., Python 3.12 loading Python 3.11 `.so` binaries).
- `[GHOST]`: "Phantom Modules". The physical files exist in `site-packages`, but there is no metadata (`top_level.txt` or `RECORD`) tracking them. This often happens when packages are forcibly injected by OS package managers (like `apt` or `macports`) and will cause `pip freeze` to miss them.
- `[BAD WRAPPER]`: Corrupted wrapper scripts. The internal Shebang points to an unexpected external Python environment (only scanned when using `--scan-wrappers`).

> [!NOTE]
> **Misalignment Deep Dive: `[CORRUPTED]` vs `[BAD WRAPPER]`**
> Both indicate a misalignment, but they happen at different levels:
> - **`[CORRUPTED]` (Internal Package Corruption)**: Happens in `site-packages/`. The package contains compiled C/C++ engine files (like `.so`) built for the wrong python version. Symptom: Triggers `ImportError` or `Segmentation Fault` when you `import` the package.
> - **`[BAD WRAPPER]` (External Script Corruption)**: Happens in `bin/`. The executable script itself has a Shebang (`#!/path/to/python`) pointing to the wrong python environment. Symptom: Triggers `ModuleNotFoundError` when you run the command in the terminal because it starts with the wrong Python engine.

## Debugging

If you encounter unexpected behavior or want to understand how EnvGuard resolves paths and categories, you can enable the debug mode by prepending `ENVGUARD_DEBUG=1` to any command.

```bash
# Debug a specific command interception
ENVGUARD_DEBUG=1 pip install requests

# Debug the doctor diagnostic report
ENVGUARD_DEBUG=1 envguard doctor
```
EnvGuard will print detailed path resolution traces and heuristic decisions in gray text to `stderr` without interfering with your workflow.
