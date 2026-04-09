"""Export query results to Excel, clipboard, and open in Excel."""

import os
import subprocess
import csv
import io
from typing import Optional

from PyQt5.QtWidgets import QApplication, QFileDialog, QMessageBox


def result_to_dataframe(result: dict):
    """Convert query result dict to a pandas DataFrame."""
    import pandas as pd
    if "columns" not in result or not result["rows"]:
        return pd.DataFrame()
    return pd.DataFrame(result["rows"], columns=result["columns"])


def export_to_excel(result: dict, parent=None, default_dir: str = "~/Documents") -> Optional[str]:
    """Export query result to an Excel file and return the path."""
    import pandas as pd
    df = result_to_dataframe(result)
    if df.empty:
        QMessageBox.warning(parent, "Export", "No data to export.")
        return None

    default_dir = os.path.expanduser(default_dir)
    os.makedirs(default_dir, exist_ok=True)
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export to Excel", os.path.join(default_dir, "query_result.xlsx"),
        "Excel Files (*.xlsx);;CSV Files (*.csv)")
    if not path:
        return None

    if path.endswith(".csv"):
        df.to_csv(path, index=False)
    else:
        df.to_excel(path, index=False, engine="openpyxl")

    return path


def open_in_excel(path: str):
    """Open a file in the default application (Excel on Windows)."""
    try:
        os.startfile(path)
    except AttributeError:
        subprocess.Popen(["open", path])  # macOS fallback


def copy_to_clipboard(result: dict):
    """Copy query result to clipboard as tab-separated text (pasteable into Excel)."""
    if "columns" not in result or not result["rows"]:
        return

    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t")
    writer.writerow(result["columns"])
    for row in result["rows"]:
        writer.writerow([str(v) if v is not None else "" for v in row])

    clipboard = QApplication.clipboard()
    clipboard.setText(output.getvalue())


def export_and_open(result: dict, parent=None, default_dir: str = "~/Documents"):
    """Export to Excel and immediately open it."""
    path = export_to_excel(result, parent, default_dir)
    if path:
        open_in_excel(path)
    return path
