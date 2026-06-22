import sys
import subprocess
import os

def test_main_execution():
    # Execute main.py via subprocess to hit the __name__ == "__main__" block
    import envguard
    main_path = os.path.join(os.path.dirname(envguard.__file__), "main.py")
    
    # Running without args should exit with an error (showing usage)
    res = subprocess.run([sys.executable, main_path], capture_output=True, text=True)
    assert res.returncode != 0
    assert "usage:" in res.stdout or "usage:" in res.stderr
