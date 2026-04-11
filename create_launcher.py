"""Generate a batch file to launch the Actuarial Bot."""

import os
import sys

def main():
    repo_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable
    bat_path = os.path.join(repo_dir, "launch.bat")

    content = f"""@echo off
cd /d "{repo_dir}"
"{python_exe}" main.py
pause
"""

    with open(bat_path, "w") as f:
        f.write(content)

    print(f"Created: {bat_path}")
    print(f"Python:  {python_exe}")
    print("Double-click launch.bat to start the Actuarial Bot.")


if __name__ == "__main__":
    main()
