import subprocess
import tempfile
import os
from typing import Optional


class PythonRunner:
    """Executes Python scripts in a subprocess and captures output."""

    def __init__(self, executable: str = "python", timeout: int = 120):
        self.executable = executable
        self.timeout = timeout

    def run(self, code: str, input_data: Optional[str] = None) -> dict:
        """Run a Python script and return stdout, stderr, and any generated files."""
        with tempfile.TemporaryDirectory(prefix="actbot_") as tmpdir:
            script_path = os.path.join(tmpdir, "script.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            # If there's input data (e.g., CSV), write it to a file the script can access
            if input_data:
                data_path = os.path.join(tmpdir, "input_data.csv")
                with open(data_path, "w", encoding="utf-8") as f:
                    f.write(input_data)

            try:
                result = subprocess.run(
                    [self.executable, script_path],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=tmpdir,
                    env={**os.environ, "ACTBOT_TMPDIR": tmpdir},
                )

                # Check for any output files generated
                output_files = []
                for fname in os.listdir(tmpdir):
                    if fname not in ("script.py", "input_data.csv"):
                        fpath = os.path.join(tmpdir, fname)
                        if os.path.isfile(fpath):
                            output_files.append({"name": fname, "path": fpath, "size": os.path.getsize(fpath)})

                # Copy output files to a persistent location if they exist
                persistent_files = []
                if output_files:
                    persist_dir = os.path.join(os.path.expanduser("~"), "Documents", "actuarial-bot-output")
                    os.makedirs(persist_dir, exist_ok=True)
                    import shutil
                    for of in output_files:
                        dest = os.path.join(persist_dir, of["name"])
                        shutil.copy2(of["path"], dest)
                        persistent_files.append({"name": of["name"], "path": dest, "size": of["size"]})

                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "return_code": result.returncode,
                    "output_files": persistent_files,
                }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Script timed out after {self.timeout} seconds.",
                    "return_code": -1,
                    "output_files": [],
                }
            except Exception as e:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": str(e),
                    "return_code": -1,
                    "output_files": [],
                }
