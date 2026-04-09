"""Main PyQt5 chat window for the Actuarial Bot."""

import threading
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QScrollArea, QLabel, QStatusBar, QMenuBar,
    QAction, QMessageBox, QSplitter, QApplication,
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QKeyEvent

from core.agent import ActuarialAgent
from ui.message_widgets import (
    ChatBubble, SQLBlock, ResultTable, WarningBanner, ToolCallIndicator,
)
from ui.export import copy_to_clipboard, export_to_excel, export_and_open


class AgentSignals(QObject):
    """Signals for thread-safe communication from agent thread to UI."""
    chunk = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)


class ChatInput(QTextEdit):
    """Custom text input that sends on Enter (Shift+Enter for newline)."""
    submitted = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
            self.submitted.emit()
        else:
            super().keyPressEvent(event)


class ChatWindow(QMainWindow):
    def __init__(self, agent: ActuarialAgent, config: dict):
        super().__init__()
        self.agent = agent
        self.config = config
        self.is_processing = False
        self.signals = AgentSignals()
        self.signals.chunk.connect(self._handle_chunk)
        self.signals.finished.connect(self._on_finished)
        self.signals.error.connect(self._on_error)

        self._setup_ui()
        self._setup_menu()

    def _setup_ui(self):
        self.setWindowTitle("Actuarial Bot")
        self.setMinimumSize(900, 700)
        self.setStyleSheet("""
            QMainWindow { background-color: #1E1E1E; }
            QStatusBar { background-color: #007ACC; color: white; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Chat scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: #1E1E1E; }
            QScrollBar:vertical {
                background-color: #1E1E1E;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background-color: #424242;
                border-radius: 5px;
                min-height: 20px;
            }
        """)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch()
        self.scroll_area.setWidget(self.chat_container)

        layout.addWidget(self.scroll_area, stretch=1)

        # Input area
        input_frame = QWidget()
        input_frame.setStyleSheet("background-color: #252526;")
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 8, 12, 8)

        self.input_box = ChatInput()
        self.input_box.setPlaceholderText("Ask about your data... (Enter to send, Shift+Enter for newline)")
        self.input_box.setFont(QFont("Segoe UI", 12))
        self.input_box.setMaximumHeight(100)
        self.input_box.setStyleSheet("""
            QTextEdit {
                background-color: #3C3C3C;
                color: #D4D4D4;
                border: 1px solid #555;
                border-radius: 8px;
                padding: 8px;
            }
            QTextEdit:focus { border-color: #007ACC; }
        """)
        self.input_box.submitted.connect(self._send_message)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFixedSize(70, 40)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1177BB; }
            QPushButton:disabled { background-color: #3C3C3C; color: #808080; }
        """)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        layout.addWidget(input_frame)

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready — Connected to Oracle")

        # Welcome message
        self._add_widget(ChatBubble(
            "Hello! I'm your actuarial data assistant. I can query your Oracle database, "
            "analyze data, and help you understand insurance metrics.\n\n"
            "Try asking something like:\n"
            "  - \"What tables contain premium data?\"\n"
            "  - \"What is the loss ratio for the BOP line?\"\n"
            "  - \"Show me the top 10 policies by earned premium\"\n"
            "  - \"Export the results to Excel\"",
            is_user=False,
        ))

    def _setup_menu(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar { background-color: #2D2D30; color: #D4D4D4; }
            QMenuBar::item:selected { background-color: #094771; }
            QMenu { background-color: #2D2D30; color: #D4D4D4; }
            QMenu::item:selected { background-color: #094771; }
        """)

        # Chat menu
        chat_menu = menubar.addMenu("Chat")
        new_chat = QAction("New Conversation", self)
        new_chat.setShortcut("Ctrl+N")
        new_chat.triggered.connect(self._new_conversation)
        chat_menu.addAction(new_chat)

        # Export menu
        export_menu = menubar.addMenu("Export")
        export_excel_action = QAction("Last Result to Excel...", self)
        export_excel_action.setShortcut("Ctrl+E")
        export_excel_action.triggered.connect(self._export_last_result)
        export_menu.addAction(export_excel_action)

        copy_action = QAction("Copy Last Result", self)
        copy_action.setShortcut("Ctrl+Shift+C")
        copy_action.triggered.connect(self._copy_last_result)
        export_menu.addAction(copy_action)

    def _add_widget(self, widget):
        """Add a widget to the chat layout before the stretch."""
        count = self.chat_layout.count()
        self.chat_layout.insertWidget(count - 1, widget)
        # Scroll to bottom
        QApplication.processEvents()
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _send_message(self):
        text = self.input_box.toPlainText().strip()
        if not text or self.is_processing:
            return

        self.input_box.clear()
        self._add_widget(ChatBubble(text, is_user=True))

        self.is_processing = True
        self.send_btn.setEnabled(False)
        self.status.showMessage("Thinking...")

        # Run agent in background thread
        thread = threading.Thread(target=self._run_agent, args=(text,), daemon=True)
        thread.start()

    def _run_agent(self, message: str):
        try:
            for chunk in self.agent.chat(message):
                self.signals.chunk.emit(chunk)
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()

    def _handle_chunk(self, chunk: dict):
        msg_type = chunk["type"]

        if msg_type == "text":
            self._add_widget(ChatBubble(chunk["content"], is_user=False))

        elif msg_type == "tool_call":
            self._add_widget(ToolCallIndicator(chunk["name"]))
            self.status.showMessage(f"Running: {chunk['name']}...")

        elif msg_type == "sql_preview":
            self._add_widget(SQLBlock(chunk["sql"], chunk.get("explanation", "")))

        elif msg_type == "query_result":
            result = chunk["result"]
            if result.get("columns") and result.get("rows"):
                table_widget = ResultTable(
                    result["columns"], result["rows"],
                    max_display=self.config.get("ui", {}).get("max_table_rows_display", 500),
                )
                table_widget.export_clipboard.connect(lambda: copy_to_clipboard(result))
                table_widget.export_excel.connect(
                    lambda: export_to_excel(result, self, self.config.get("export", {}).get("default_directory", "~/Documents")))
                table_widget.open_excel.connect(
                    lambda: export_and_open(result, self, self.config.get("export", {}).get("default_directory", "~/Documents")))
                self._add_widget(table_widget)

        elif msg_type == "warning":
            self._add_widget(WarningBanner(chunk["content"]))

        elif msg_type == "python_result":
            result = chunk["result"]
            if result.get("stdout"):
                self._add_widget(ChatBubble(f"Python output:\n{result['stdout'][:3000]}", is_user=False))
            if result.get("stderr") and not result.get("success"):
                self._add_widget(WarningBanner(f"Python error:\n{result['stderr'][:2000]}"))
            if result.get("output_files"):
                files = ", ".join(f["name"] for f in result["output_files"])
                self._add_widget(ChatBubble(f"Generated files: {files}", is_user=False))

        elif msg_type == "tool_result":
            pass  # Tool results are consumed by the agent, not shown directly

        elif msg_type == "error":
            self._add_widget(WarningBanner(f"Error: {chunk['content']}"))

    def _on_finished(self):
        self.is_processing = False
        self.send_btn.setEnabled(True)
        self.status.showMessage("Ready")
        self.input_box.setFocus()

    def _on_error(self, msg: str):
        self._add_widget(WarningBanner(f"Error: {msg}"))

    def _new_conversation(self):
        reply = QMessageBox.question(
            self, "New Conversation", "Clear chat history and start fresh?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.agent.reset_conversation()
            # Clear chat widgets
            while self.chat_layout.count() > 1:
                item = self.chat_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._add_widget(ChatBubble("Conversation cleared. How can I help?", is_user=False))

    def _export_last_result(self):
        if self.agent.last_result:
            export_to_excel(self.agent.last_result, self,
                            self.config.get("export", {}).get("default_directory", "~/Documents"))
        else:
            QMessageBox.information(self, "Export", "No query results to export yet.")

    def _copy_last_result(self):
        if self.agent.last_result:
            copy_to_clipboard(self.agent.last_result)
            self.status.showMessage("Copied to clipboard!", 3000)
        else:
            self.status.showMessage("No results to copy", 3000)
