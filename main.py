"""Actuarial Bot — Entry Point"""

import sys
import os
import yaml
from dotenv import load_dotenv
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtGui import QFont, QPixmap, QColor, QPainter
from PyQt5.QtCore import Qt


def load_config() -> dict:
    """Load config from config.local.yaml (user-specific) or config.yaml (defaults).
    Environment variables from .env override config file values."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base_dir, ".env"))

    # Try local config first, fall back to default
    for name in ("config.local.yaml", "config.yaml"):
        path = os.path.join(base_dir, name)
        if os.path.exists(path):
            with open(path, "r") as f:
                config = yaml.safe_load(f)
            print(f"Loaded config from {name}")

            # Override with environment variables if present
            if os.getenv("OPENAI_KEY"):
                config.setdefault("openai", {})["api_key"] = os.getenv("OPENAI_KEY")
            if os.getenv("ORACLE_DSN"):
                config.setdefault("oracle", {})["dsn"] = os.getenv("ORACLE_DSN")
            if os.getenv("ORACLE_USER"):
                config.setdefault("oracle", {})["user"] = os.getenv("ORACLE_USER")
            if os.getenv("ORACLE_PASSWORD"):
                config.setdefault("oracle", {})["password"] = os.getenv("ORACLE_PASSWORD")

            return config

    print("ERROR: No config file found. Copy config.yaml to config.local.yaml and fill in credentials.")
    sys.exit(1)


def validate_config(config: dict) -> list[str]:
    """Check for required config values. Returns list of errors."""
    errors = []
    openai_cfg = config.get("openai", {})
    if not openai_cfg.get("api_key") or openai_cfg["api_key"].startswith("YOUR_"):
        errors.append("OpenAI API key not configured")

    oracle_cfg = config.get("oracle", {})
    if not oracle_cfg.get("dsn") or oracle_cfg["dsn"].startswith("YOUR_"):
        errors.append("Oracle DSN not configured")
    if not oracle_cfg.get("user") or oracle_cfg["user"].startswith("YOUR_"):
        errors.append("Oracle username not configured")
    if not oracle_cfg.get("password") or oracle_cfg["password"].startswith("YOUR_"):
        errors.append("Oracle password not configured")

    return errors


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 11))
    app.setStyle("Fusion")

    # Dark palette
    from PyQt5.QtGui import QPalette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.Base, QColor(37, 37, 38))
    palette.setColor(QPalette.AlternateBase, QColor(45, 45, 48))
    palette.setColor(QPalette.ToolTipBase, QColor(30, 30, 30))
    palette.setColor(QPalette.ToolTipText, QColor(212, 212, 212))
    palette.setColor(QPalette.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.Button, QColor(45, 45, 48))
    palette.setColor(QPalette.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.Link, QColor(86, 156, 214))
    palette.setColor(QPalette.Highlight, QColor(14, 99, 156))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    # Load config
    config = load_config()

    # Check if Oracle is configured
    oracle_cfg = config.get("oracle", {})
    oracle_configured = (
        oracle_cfg.get("dsn") and not oracle_cfg["dsn"].startswith("YOUR_")
        and oracle_cfg.get("user") and not oracle_cfg["user"].startswith("YOUR_")
        and oracle_cfg.get("password") and not oracle_cfg["password"].startswith("YOUR_")
    )

    # Validate OpenAI key is present
    openai_cfg = config.get("openai", {})
    if not openai_cfg.get("api_key") or openai_cfg["api_key"].startswith("YOUR_"):
        QMessageBox.critical(None, "Configuration Error", "OpenAI API key not configured in .env or config.local.yaml.")
        sys.exit(1)

    # Initialize components
    from db.connection import OracleConnection
    from executor.python_runner import PythonRunner
    from core.agent import ActuarialAgent
    from ui.chat_window import ChatWindow

    oracle_conn = None
    if oracle_configured:
        oracle_conn = OracleConnection(
            dsn=oracle_cfg["dsn"],
            user=oracle_cfg["user"],
            password=oracle_cfg["password"],
        )
        try:
            oracle_conn.connect()
            print("Oracle connection successful")
        except Exception as e:
            print(f"Warning: Oracle connection failed: {e}")
            print("Running in demo mode (no database)")
            oracle_conn = None
    else:
        print("Oracle not configured — running in demo mode (no database)")

    python_cfg = config.get("python", {})
    python_runner = PythonRunner(
        executable=python_cfg.get("executable", "python"),
        timeout=python_cfg.get("timeout", 120),
    )

    openai_cfg = config["openai"]
    agent = ActuarialAgent(
        api_key=openai_cfg["api_key"],
        model=openai_cfg.get("model", "gpt-4o"),
        oracle_conn=oracle_conn,
        python_runner=python_runner,
        temperature=openai_cfg.get("temperature", 0.1),
        max_tokens=openai_cfg.get("max_tokens", 4096),
    )
    agent.max_rows = oracle_cfg.get("max_rows", 10000)

    # Auto-discover schemas if connected
    if oracle_conn:
        schemas = oracle_cfg.get("schemas", [])
        if schemas:
            for schema in schemas:
                try:
                    tables = agent.schema.discover_tables(schema)
                    print(f"Discovered {len(tables)} tables in schema {schema}")
                except Exception as e:
                    print(f"Warning: Could not discover schema {schema}: {e}")

    # Launch UI
    window = ChatWindow(agent, config)
    if not oracle_conn:
        window.status.showMessage("Demo Mode — No Oracle connection (chat and Python still work)")
    window.show()

    ret = app.exec_()
    if oracle_conn:
        oracle_conn.close()
    sys.exit(ret)


if __name__ == "__main__":
    main()
