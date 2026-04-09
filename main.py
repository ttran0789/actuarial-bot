"""Actuarial Bot — Entry Point"""

import sys
import os
import yaml
from dotenv import load_dotenv
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt


def load_config() -> dict:
    """Load config from config.local.yaml (user-specific) or config.yaml (defaults).
    Environment variables from .env override config file values."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base_dir, ".env"))

    for name in ("config.local.yaml", "config.yaml"):
        path = os.path.join(base_dir, name)
        if os.path.exists(path):
            with open(path, "r") as f:
                config = yaml.safe_load(f)

            # Migrate old 'openai' config key to 'ai' if needed
            if "openai" in config and "ai" not in config:
                config["ai"] = config.pop("openai")
                config["ai"]["provider"] = "openai"

            # Override with environment variables
            ai = config.setdefault("ai", {})
            if os.getenv("OPENAI_KEY"):
                ai["api_key"] = os.getenv("OPENAI_KEY")
            if os.getenv("AZURE_OPENAI_KEY"):
                ai["api_key"] = os.getenv("AZURE_OPENAI_KEY")
                ai.setdefault("provider", "azure")
            if os.getenv("AZURE_OPENAI_ENDPOINT"):
                ai["azure_endpoint"] = os.getenv("AZURE_OPENAI_ENDPOINT")
            if os.getenv("AI_BASE_URL"):
                ai["base_url"] = os.getenv("AI_BASE_URL")
                ai.setdefault("provider", "custom")

            oracle = config.setdefault("oracle", {})
            if os.getenv("ORACLE_DSN"):
                oracle["dsn"] = os.getenv("ORACLE_DSN")
            if os.getenv("ORACLE_USER"):
                oracle["user"] = os.getenv("ORACLE_USER")
            if os.getenv("ORACLE_PASSWORD"):
                oracle["password"] = os.getenv("ORACLE_PASSWORD")

            return config

    print("ERROR: No config file found. Copy config.yaml to config.local.yaml and fill in credentials.")
    sys.exit(1)


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

    # Setup logging
    from core.logging_config import setup_logging
    log_cfg = config.get("logging", {})
    log = setup_logging(
        log_dir=log_cfg.get("log_dir"),
        level=log_cfg.get("level", "INFO"),
    )
    log.info("Actuarial Bot starting")
    log.info("AI provider: %s, model: %s", config["ai"].get("provider", "openai"), config["ai"].get("model", "gpt-4o"))

    # Validate AI key
    ai_cfg = config.get("ai", {})
    if not ai_cfg.get("api_key") or ai_cfg["api_key"].startswith("YOUR_"):
        QMessageBox.critical(None, "Configuration Error", "AI API key not configured in .env or config.local.yaml.")
        sys.exit(1)

    # Create LLM client
    from core.llm_client import create_llm_client
    try:
        llm_client, model_name = create_llm_client(ai_cfg)
    except Exception as e:
        log.error("Failed to create LLM client: %s", e)
        QMessageBox.critical(None, "AI Configuration Error", f"Could not initialize AI client:\n\n{e}")
        sys.exit(1)

    # Oracle connection
    from db.connection import OracleConnection
    oracle_cfg = config.get("oracle", {})
    oracle_configured = (
        oracle_cfg.get("dsn") and not oracle_cfg["dsn"].startswith("YOUR_")
        and oracle_cfg.get("user") and not oracle_cfg["user"].startswith("YOUR_")
        and oracle_cfg.get("password") and not oracle_cfg["password"].startswith("YOUR_")
    )

    oracle_conn = None
    if oracle_configured:
        oracle_conn = OracleConnection(
            dsn=oracle_cfg["dsn"],
            user=oracle_cfg["user"],
            password=oracle_cfg["password"],
        )
        try:
            oracle_conn.connect()
            log.info("Oracle connection successful (DSN: %s)", oracle_cfg["dsn"])
        except Exception as e:
            log.warning("Oracle connection failed: %s", e)
            oracle_conn = None
    else:
        log.info("Oracle not configured — running in demo mode")

    # Python executor
    from executor.python_runner import PythonRunner
    python_cfg = config.get("python", {})
    python_runner = PythonRunner(
        executable=python_cfg.get("executable", "python"),
        timeout=python_cfg.get("timeout", 120),
    )

    # Agent
    from core.agent import ActuarialAgent
    agent = ActuarialAgent(
        client=llm_client,
        model=model_name,
        oracle_conn=oracle_conn,
        python_runner=python_runner,
        temperature=ai_cfg.get("temperature", 0.1),
        max_tokens=ai_cfg.get("max_tokens", 4096),
    )
    agent.max_rows = oracle_cfg.get("max_rows", 10000)

    # Auto-discover schemas if connected
    if oracle_conn:
        schemas = oracle_cfg.get("schemas", [])
        if schemas:
            for schema in schemas:
                try:
                    tables = agent.schema.discover_tables(schema)
                    log.info("Discovered %d tables in schema %s", len(tables), schema)
                except Exception as e:
                    log.warning("Could not discover schema %s: %s", schema, e)

    # Launch UI
    from ui.chat_window import ChatWindow
    window = ChatWindow(agent, config)
    if not oracle_conn:
        window.status.showMessage("Demo Mode — No Oracle connection (chat and Python still work)")
    window.show()
    log.info("UI launched")

    ret = app.exec_()
    log.info("Application exiting (code=%d)", ret)
    if oracle_conn:
        oracle_conn.close()
    sys.exit(ret)


if __name__ == "__main__":
    main()
