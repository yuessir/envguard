# Contributing to EnvGuard

Welcome! We are thrilled that you are interested in contributing to EnvGuard.

EnvGuard is a tool designed to silently protect developers' environments without ever getting in their way. Because it interacts deeply with shell hooks and system paths, we have a very strict, highly disciplined engineering culture. 

This document outlines the Standard Operating Procedure (SOP) and development philosophy established during Phase 1. Please read it carefully before submitting a Pull Request.

---

## 1. Core Engineering Philosophy

### 1.1 Silent Fail is Non-Negotiable
EnvGuard is a passive protector. If our tool crashes, lacks permissions, or encounters a bizarre edge case, **it must degrade gracefully and silently**. 
* Never block the user's original command (e.g., `pip install`).
* All entry points (`hook.py`, `cli.py`, shell wrappers) must wrap execution in broad `try-except` blocks.
* If an error occurs, log it to `logger.debug` and exit quietly.

### 1.2 Shell Hooks Must Be Dumb
Shell scripting (`zsh`, `bash`) is notoriously fragile across different OS versions. 
* Keep `.plugin.zsh` and `.bash` wrappers as thin as possible.
* Their only job is to intercept the command, bypass aliases to find the real executable (`whence -p` / `type -P`), and pass the arguments to Python.
* **All** complex path resolution, string parsing, and heuristic logic must happen in Python.

### 1.3 Separation of Concerns (UI vs. Engine)
* **Engine (`engine.py`, `hook.py`):** Strictly responsible for data. It returns standardized data structures (`dict`, `JSON`). It must never print to standard output or contain ANSI color codes.
* **CLI (`cli.py`):** Strictly responsible for presentation. It consumes the Engine's dictionaries and renders them with colors, formatting, and warnings.

---

## 2. Test-Driven Development (TDD) SOP

We practice strict TDD. Because environment resolution is highly dependent on edge cases, **you must write the tests before touching the implementation.**

### Step 1: Write the Test and Define the Edge Case
Before modifying `engine.py` or `hook.py`, go to the `tests/` directory.
Use `pytest` and `unittest.mock.patch` to simulate the environment:
* Mock `os.path.realpath` to simulate symlinks.
* Mock `shutil.which` to simulate command locations.
* Use `tmp_path` to create fake directory structures (e.g., fake `.venv/bin` with a dummy `pyvenv.cfg`).

### Step 2: Watch it Fail
Run `pytest` to confirm your new test fails (because the logic doesn't exist yet).

### Step 3: Implement the Logic
Write the minimum amount of code in `src/envguard/` required to make your test pass.

### Step 4: Run the Full Suite
Ensure you haven't broken any existing behavior:
```bash
python3 -m pytest tests/
```

---

## 3. Debugging and Tracing

Do not use `print()` for debugging in the engine. 
Use the built-in logger:
```python
from envguard import logger
logger.debug("Tracing symlink resolution...")
```
When developing locally, you can view your traces by prepending `ENVGUARD_DEBUG=1` to your commands:
```bash
ENVGUARD_DEBUG=1 envguard doctor
```

---

## 4. Submitting a Pull Request

Before submitting a PR, ensure you have completed the following checklist:

1. **Tests Added:** Every new feature or bug fix must be accompanied by a unit test.
2. **Linting Passed:** We use `flake8`. Run it locally:
   ```bash
   flake8 src tests --count --select=E9,F63,F7,F82 --show-source --statistics
   ```
3. **CI/CD Green:** Your PR will automatically trigger our GitHub Actions workflow. Ensure all tests pass on the CI server.
4. **Idempotency Checked:** If you are modifying the shell installation scripts (`init`), ensure your script can be run 100 times without duplicating lines in the user's `~/.zshrc`.

Thank you for helping us keep Python environments clean and safe!
