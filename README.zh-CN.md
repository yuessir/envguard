# EnvGuard

[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

EnvGuard 是一个适用于 Python 的跨环境 CLI 拦截器与路径冲突诊断工具。
它能防止因全局工具、系统环境与虚拟环境 (`venv`) 之间路径错位所造成的常见问题。

## 核心功能 (Core Features)
- **被动防护 (Passive Guard):** 如果在错误的环境下执行高风险指令（如 `pip install`, `pyinstaller`），EnvGuard 会立刻拦截。
- **主动诊断 (Proactive Diagnostics):** 提供 `envguard doctor` 指令，扫描并回报环境的健康状态。
- **模块雷达 (Module Radar):** 提供 `envguard find <module_name>` 指令，跨越本地、虚拟环境与 10 种以上的全局环境（Conda, Pyenv, MacPorts, Homebrew 等）定位 Python 软件包。
- **动态软件包分析 (Dynamic Package Analysis):** 自动扫描 Python 软件包的实体内容与源代码，将其分类为 `纯 Python (原生)`、`纯 Python (系统包装)` 或 `C-扩展模块`，消除“底层可执行文件到底在哪？”的困惑。
- **隔离审计 (Isolation Audit):** 深度扫描环境，检测越界依赖、内部文件损坏以及“幽灵模块”（缺乏 metadata 的软件包）。
- **智能安全网 (Smart Safety Nets):** 警告不当使用 `--break-system-packages`，并在非交互式 CI/CD 环境中立即中止执行。

## 安装方式 (Installation)

```bash
# 1. 透过 pip 或 uv 安装
pip install envguard
# 或
uv pip install envguard

# 2. 初始化 shell hooks (Zsh/Bash)
envguard init

# 3. 重启终端或重新加载 rc 文件
source ~/.zshrc
```

## 配置方式 (`~/.envguard/config.json`)

EnvGuard 的保护机制完全是**配置驱动 (Configuration-Driven)** 的。执行 `envguard init` 后，会自动在 `~/.envguard/config.json` 产生一份默认的配置文件。

您可以自定义这个 JSON 文件，加入任何您想要 EnvGuard 拦截与保护的命令行工具。它是一个通用的安全网，甚至能完美适用于非 Python 的系统工具（如 `brew`, `port`, `npm`）。

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
> **零延迟 Shell Hooks 与热重载 (Hot-Reloading)**
> EnvGuard 的 shell hooks 专为 0ms 终端启动延迟而设计。在编辑完 `config.json` 后，您**必须再次执行 `envguard init`**，将变更编译为纯文本缓存 (`~/.envguard/tools.cache`)。
> **主动同步与热重载:** 如果您忘记同步，任何 `envguard` 指令都会主动显示智能提示。一旦执行 `envguard init`，EnvGuard 会立即将新的 hooks **热重载** 到您目前的终端中——完全不需打开新标签页或重启 shell！

### 进阶规则 (`rules.json`)
EnvGuard 依赖内部的 `rules.json` 文件来执行高级的启发式扫描，例如定义 `ghost_whitelist` (用于忽略安全的无 metadata 模块，如 `sitecustomize` 或 `__pycache__`) 以及定义搜索时的 `blacklist_directories`。如果您需要跳过特定幽灵模块的误判，可以在源代码中自定义此文件。

## 使用方式与示例 (Usage & Examples)

初始化完成后，EnvGuard 会在后台安静地运作。只有在检测到严重的环境错位时，才会跳出来打断您。

### 1. 主动诊断 (`envguard doctor`)
随时执行此指令，深入分析目前的 Python 环境，并验证常用工具（如 `pip`, `pytest` 等）是否正确对齐。

```bash
envguard doctor
```
**输出示例:**
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
*(EnvGuard 会明确区分您的“Alias (别名)”与“Real (真实)”可执行文件路径，让您不再被 symlink 欺骗。)*

### 2. 被动防护 (Passive Guard)
如果您的 `$PATH` 配置有误，导致您不小心执行了属于不同 Python 版本的工具（例如：在 Python 3.12 环境下执行了 3.9 版的 `pip`），EnvGuard 会立即拦截：

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

### 3. 模块雷达 (`envguard find`)
您是否曾经遇过明明执行过 `pip install`，却还是出现 `ModuleNotFoundError`？EnvGuard 提供强大的 3 层搜索引擎，可扫描您的本地工作区、活动中的虚拟环境，以及所有已知的系统全局环境（由 `rules.json` 驱动）。

> [!NOTE]
> **Python 模块名称 vs. OS 软件包名称**
> `envguard find` 专为搜索 **Python 模块名称** (例如 `numpy`) 而设计，这正是您在 `import` 时输入的确切名称。请勿搜索 OS 软件包管理器的名称（如 `py312-numpy` 或 `python3-numpy`）。EnvGuard 会直接扫描 `site-packages` 目录寻找实际的 Python 源代码。

```bash
envguard find cv2
```
**输出示例:**
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
*(自动解析常见的 import 名称如 `cv2` -> `opencv-python`，并对软件包的实体结构进行分类，让您瞬间明白它是否捆绑了 C 引擎，还是封装了外部的 OS 指令。)*

**软件包类型解释:**
EnvGuard 就像 Python 软件包的 X 光机，将它们分类为三种不同的类型，帮助您排解“缺少可执行文件”或“缺少引擎”的错误：
- `📦 Pure Python (Native)`: 100% Python 代码。不包含系统指令或 C-extensions。(如 `requests`, `pytest`)
- `📦 Pure Python (System Wrapper)`: 大量调用外部 OS 指令的纯 Python 代码。(如 `pytesseract`)。**诊断提示:** 如果此类软件包发生错误，请检查您的 OS `$PATH` 或包管理器 (Brew/MacPorts)，因为底层引擎“并没有”安装在您的 Python 环境中。
- `📦 C-Extension / Bundled Binary`: 内部捆绑了已编译的 C/C++ 引擎文件 (`.so`, `.dylib`, `.pyd`)。(如 `cv2`, `numpy`)。**诊断提示:** 引擎是自给自足的，您不需要安装外部的 OS 库。

### 4. 隔离审计 (`envguard audit`)
`audit` 指令会对目标 Python 环境进行深度扫描。它会迭代所有已安装的软件包，检查其物理文件、metadata 以及 site-packages 结构，以评估其隔离完整性。

```bash
# 执行分类的审计报告
envguard audit

# 显示为表格格式
envguard audit --format table

# 显示详细警告 (可查看底层的权限或探针错误)
envguard audit --verbose
```

EnvGuard 会将每个软件包分类为四种状态之一：
- `[SAFE]`: 安装正确且隔离良好。
- `[LEAK]`: 从未授权的外部环境拉取 (例如：虚拟环境偷偷加载了全局的 site-packages)。
- `[CORRUPTED]`: Python 版本与软件包内容发生内部错位 (例如：Python 3.12 加载了 Python 3.11 的 `.so` 可执行文件)。
- `[GHOST]`: “幽灵模块”。实体文件存在于 `site-packages` 中，但没有任何 metadata (`top_level.txt` 或 `RECORD`) 追踪它们。这通常发生在 OS 包管理器 (如 `apt` 或 `macports`) 强制植入软件包时，并会导致 `pip freeze` 遗漏这些依赖。

## 调试 (Debugging)

如果您遇到非预期的行为，或想了解 EnvGuard 是如何解析路径与分类的，您可以在任何指令前加上 `ENVGUARD_DEBUG=1` 来启用调试模式。

```bash
# 对特定的指令拦截进行调试
ENVGUARD_DEBUG=1 pip install requests

# 对 doctor 诊断报告进行调试
ENVGUARD_DEBUG=1 envguard doctor
```
EnvGuard 会将详细的路径解析追踪与启发式决策以灰色文本打印至 `stderr`，且不会干扰您的正常工作流程。
