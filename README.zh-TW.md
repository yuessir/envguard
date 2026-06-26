# EnvGuard

[English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

EnvGuard 是一個適用於 Python 的跨環境 CLI 攔截器與路徑衝突診斷工具。
它能防止因全域工具、系統環境與虛擬環境 (`venv`) 之間路徑錯位所造成的常見問題。

## 核心功能 (Core Features)
- **被動防護 (Passive Guard):** 如果在錯誤的環境下執行高風險指令（如 `pip install`, `pyinstaller`），EnvGuard 會立刻攔截。
- **主動診斷 (Proactive Diagnostics):** 提供 `envguard doctor` 指令，掃描並回報環境的健康狀態。
- **模組雷達 (Module Radar):** 提供 `envguard find <module_name>` 指令，跨越本地、虛擬環境與 10 種以上的全域環境（Conda, Pyenv, MacPorts, Homebrew 等）定位 Python 套件。
- **動態套件分析 (Dynamic Package Analysis):** 自動掃描 Python 套件的實體內容與原始碼，將其分類為 `純 Python (原生)`、`純 Python (系統包裝)` 或 `C-擴充套件`，消除「底層執行檔到底在哪？」的困惑。
- **隔離審計 (Isolation Audit):** 深度掃描環境，偵測越界依賴、內部檔案毀損以及「幽靈模組」（缺乏 metadata 的套件）。
- **智慧安全網 (Smart Safety Nets):** 警告不當使用 `--break-system-packages`，並在非互動式 CI/CD 環境中立即中止執行。

## 安裝方式 (Installation)

```bash
# 1. 透過 pip 或 uv 安裝
pip install envguard
# 或
uv pip install envguard

# 2. 初始化 shell hooks (Zsh/Bash)
envguard init

# 3. 重啟終端機或重新載入 rc 檔
source ~/.zshrc
```

## 設定方式 (`~/.envguard/config.json`)

EnvGuard 的保護機制完全是**配置驅動 (Configuration-Driven)** 的。執行 `envguard init` 後，會自動在 `~/.envguard/config.json` 產生一份預設的設定檔。

您可以自訂這個 JSON 檔案，加入任何您想要 EnvGuard 攔截與保護的命令列工具。它是一個通用的安全網，甚至能完美適用於非 Python 的系統工具（如 `brew`, `port`, `npm`）。

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
> **零延遲 Shell Hooks 與熱重載 (Hot-Reloading)**
> EnvGuard 的 shell hooks 專為 0ms 終端機啟動延遲而設計。在編輯完 `config.json` 後，您**必須再次執行 `envguard init`**，將變更編譯為純文字快取 (`~/.envguard/tools.cache`)。
> **主動同步與熱重載:** 如果您忘記同步，任何 `envguard` 指令都會主動顯示智慧提示。一旦執行 `envguard init`，EnvGuard 會立即將新的 hooks **熱重載** 到您目前的終端機中——完全不需開啟新分頁或重啟 shell！

### 進階規則 (`rules.json`)
EnvGuard 依賴內部的 `rules.json` 檔案來執行進階的啟發式掃描，例如定義 `ghost_whitelist` (用於忽略安全的無 metadata 模組，如 `sitecustomize` 或 `__pycache__`) 以及定義搜尋時的 `blacklist_directories`。如果您需要略過特定幽靈模組的誤判，可以在原始碼中自訂此檔案。

## 平台支援 (Platform Support)

EnvGuard 的核心邏輯完全基於 Unix/POSIX 標準設計，因此具有極佳的跨平台穩定性：

- **macOS (Intel & Apple Silicon):** ✅ 完全支援。支援 Zsh 攔截，並相容 Homebrew (`/usr/local` 或 `/opt/homebrew`) 與 MacPorts 等架構。
- **Linux (Ubuntu, Debian, CentOS 等):** ✅ 完全支援。支援 Bash/Zsh 攔截，並精準解析 `pyenv` 的墊片 (Shims) 機制。
- **Windows:** ⚠️ 部分支援 (開發中)。目前 `envguard doctor` 與 `envguard audit` 等主動診斷指令可正常運行，但尚未支援 PowerShell / CMD 的被動攔截 (Shell Hook) 功能。建議在 Windows 環境下搭配 WSL2 獲得完整體驗。

## 使用方式與範例 (Usage & Examples)
初始化完成後，EnvGuard 會在背景安靜地運作。只有在偵測到嚴重的環境錯位時，才會跳出來打斷您。

### 1. 主動診斷 (`envguard doctor`)
隨時執行此指令，深入分析目前的 Python 環境，並驗證常用工具（如 `pip`, `pytest` 等）是否正確對齊。

```bash
envguard doctor
```
**輸出範例:**
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
*(EnvGuard 會明確區分您的「Alias (別名)」與「Real (真實)」執行檔路徑，讓您不再被 symlink 欺騙。)*

### 2. 被動防護 (Passive Guard)
如果您的 `$PATH` 設定有誤，導致您不小心執行了屬於不同 Python 版本的工具（例如：在 Python 3.12 環境下執行了 3.9 版的 `pip`），EnvGuard 會立即攔截：

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

**AB 車錯位警告 (Wrapper Integrity Check):**
除了檢查外部執行的 Python 版本，EnvGuard 也會深度檢查「執行檔墊片 (Wrapper Script)」。如果它發現您執行的指令（例如 `jupyter`）所在資料夾的版本，與它內部 Shebang (`#!/path/to/python`) 真正呼叫的版本不一致時，會提出「結構異常」警告。這能有效防止您在 A 環境執行指令，卻把套件裝到 B 環境的詭異現象。

> [!NOTE]
> **Hook 的攔截極限與生命週期**
> 1. **攔截極限**：EnvGuard 的動態 Hook 是透過 Zsh/Bash 的 `function` 實現。因此，它**只能攔截純指令** (例如輸入 `jupyter`)。如果您輸入的是相對/絕對路徑 (例如 `./jupyter` 或 `/bin/jupyter`)，Shell 會強制繞過 Function 直接執行實體檔案，此時 Hook **不會**被觸發。
> 2. **生命週期**：當終端機開啟時，EnvGuard 會根據名單 (預設為 `~/.envguard/tools.cache`) 綁定攔截函式。如果您修改了 `rules.json` 以新增或移除監聽工具，當下的終端機並不會立刻知道！您必須執行 `envguard init` 重新熱重載 (Hot-reload)，攔截網才會根據新名單更新。

### 3. 模組雷達 (`envguard find`)
您是否曾經遇過明明執行過 `pip install`，卻還是出現 `ModuleNotFoundError`？EnvGuard 提供強大的 3 層搜尋引擎，可掃描您的本地工作區、作用中的虛擬環境，以及所有已知的系統全域環境（由 `rules.json` 驅動）。

> [!NOTE]
> **Python 模組名稱 vs. OS 套件名稱**
> `envguard find` 專為搜尋 **Python 模組名稱** (例如 `numpy`) 而設計，這正是您在 `import` 時輸入的確切名稱。請勿搜尋 OS 套件管理器的名稱（如 `py312-numpy` 或 `python3-numpy`）。EnvGuard 會直接掃描 `site-packages` 目錄尋找實際的 Python 原始碼。

```bash
envguard find cv2
```
**輸出範例:**
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
*(自動解析常見的 import 名稱如 `cv2` -> `opencv-python`，並對套件的實體結構進行分類，讓您瞬間明白它是否綑綁了 C 引擎，還是封裝了外部的 OS 指令。)*

**套件類型解釋:**
EnvGuard 就像 Python 套件的 X 光機，將它們分類為三種不同的類型，幫助您排解「缺少執行檔」或「缺少引擎」的錯誤：
- `📦 Pure Python (Native)`: 100% Python 程式碼。不包含系統指令或 C-extensions。(如 `requests`, `pytest`)
- `📦 Pure Python (System Wrapper)`: 大量呼叫外部 OS 指令的純 Python 程式碼。(如 `pytesseract`)。**診斷提示:** 如果此類套件發生錯誤，請檢查您的 OS `$PATH` 或套件管理器 (Brew/MacPorts)，因為底層引擎「並沒有」安裝在您的 Python 環境中。
- `📦 C-Extension / Bundled Binary`: 內部綑綁了已編譯的 C/C++ 引擎檔案 (`.so`, `.dylib`, `.pyd`)。(如 `cv2`, `numpy`)。**診斷提示:** 引擎是自給自足的，您不需要安裝外部的 OS 函式庫。

### 4. 隔離審計 (`envguard audit`)
`audit` 指令會對目標 Python 環境進行深度掃描。它會迭代所有已安裝的套件，檢查其物理檔案、metadata 以及 site-packages 結構，以評估其隔離完整性。

```bash
# 執行分類的審計報告
envguard audit

# 顯示為表格格式
envguard audit --format table

# 深度掃描損壞的墊片腳本 (Shebang 錯位)
envguard audit --scan-wrappers

# 顯示詳細警告 (可查看底層的權限或探針錯誤)
envguard audit --verbose
```

> [!TIP]
> **為什麼需要靜態掃描 `--scan-wrappers`？**
> 如同前述，動態 Hook 無法攔截帶有路徑的指令 (如 `./jupyter`)。這時您可以利用 `--scan-wrappers` 進行全域的靜態健檢。它會逐一讀取環境中 `bin/` 目錄下的所有二進位墊片，揪出任何指向外部環境的 **[BAD WRAPPER]**！

EnvGuard 會將每個套件分類為五種狀態之一：
- `[SAFE]`: 安裝正確且隔離良好。
- `[LEAK]`: 從未授權的外部環境拉取 (例如：虛擬環境偷偷載入了全域的 site-packages)。
- `[CORRUPTED]`: Python 版本與套件內容發生內部錯位 (例如：Python 3.12 載入了 Python 3.11 的 `.so` 執行檔)。
- `[GHOST]`: 「幽靈模組」。實體檔案存在於 `site-packages` 中，但沒有任何 metadata (`top_level.txt` 或 `RECORD`) 追蹤它們。這通常發生在 OS 套件管理器 (如 `apt` 或 `macports`) 強制植入套件時，並會導致 `pip freeze` 遺漏這些依賴。
- `[BAD WRAPPER]`: 損壞的執行檔墊片。腳本內部的 Shebang 指向了外部非預期的 Python 環境 (僅在執行 `--scan-wrappers` 時掃描)。

> [!NOTE]
> **錯位解析：`[CORRUPTED]` 與 `[BAD WRAPPER]` 的差異**
> 兩者皆為環境錯位，但發生在不同層面：
> - **`[CORRUPTED]` (內部套件內容錯位)**：發生在 `site-packages/`。套件內包含了編譯錯誤的 C/C++ 引擎 (如 `.so`)。症狀：執行 `import` 時發生 `ImportError` 或 `Segmentation Fault`。
> - **`[BAD WRAPPER]` (外部執行檔墊片錯位)**：發生在 `bin/`。執行檔本身的 Shebang (`#!/path/to/python`) 指向錯誤的環境。症狀：在終端機輸入指令時，由於使用錯誤的 Python 引擎啟動，導致發生 `ModuleNotFoundError`。
> 
> **範例對比：**
> - 🟢 **`[SAFE]`**: 腳本 `/venv/bin/pip`，其 Shebang 指向 `#!/venv/bin/python` (向內指向同一環境)。
> - 🔴 **`[BAD WRAPPER]`**: 腳本 `/venv/bin/pip`，其 Shebang 卻指向 `#!/usr/bin/python` (向外指向外部環境)。

## 常見問題與行為 (FAQ / Known Behaviors)

### 為什麼我會看到 `[EnvGuard Warning] Detected alias for 'pip'...`？
這表示 EnvGuard 偵測到您在 `~/.zshrc` 或 `~/.bashrc` 中手動設定了別名（例如 `alias pip=pip3`）或 Shell 函式（例如 conda/nvm 相關函式）。
為了尊重您的客製化環境並防止破壞您的開發工作流，EnvGuard 會**主動退讓**，拒絕攔截並覆蓋該指令。
*   **這樣防護會失效嗎？** 完全不會！當您的別名展開為 `pip3` 並執行時，EnvGuard 會精準地攔截並保護底層的 `pip3`。
*   **如何消除這個警告？** 安裝 EnvGuard 後，您已經擁有原生的防錯位機制，不再需要手動將 `pip` 別名至 `pip3`。只需從您的 Shell 設定檔中刪除該別名，重啟終端機並再次執行 `envguard init` 即可。

## 除錯 (Debugging)

如果您遇到非預期的行為，或想了解 EnvGuard 是如何解析路徑與分類的，您可以在任何指令前加上 `ENVGUARD_DEBUG=1` 來啟用除錯模式。

```bash
# 對特定的指令攔截進行除錯
ENVGUARD_DEBUG=1 pip install requests

# 對 doctor 診斷報告進行除錯
ENVGUARD_DEBUG=1 envguard doctor
```
EnvGuard 會將詳細的路徑解析追蹤與啟發式決策以灰色文字印出至 `stderr`，且不會干擾您的正常工作流程。
