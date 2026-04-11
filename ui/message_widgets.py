"""Custom widgets for chat messages: text bubbles, SQL blocks, data tables."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QHeaderView, QFrame, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter, QPixmap


class SQLHighlighter(QSyntaxHighlighter):
    """Basic SQL syntax highlighter."""

    KEYWORDS = [
        "SELECT", "FROM", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
        "ON", "AND", "OR", "NOT", "IN", "BETWEEN", "LIKE", "IS", "NULL",
        "GROUP", "BY", "ORDER", "HAVING", "UNION", "ALL", "DISTINCT",
        "AS", "WITH", "CASE", "WHEN", "THEN", "ELSE", "END",
        "SUM", "COUNT", "AVG", "MIN", "MAX", "COALESCE", "NVL",
        "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP",
        "FETCH", "FIRST", "ROWS", "ONLY", "ASC", "DESC",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.keyword_fmt = QTextCharFormat()
        self.keyword_fmt.setForeground(QColor("#569CD6"))
        self.keyword_fmt.setFontWeight(QFont.Bold)

        self.string_fmt = QTextCharFormat()
        self.string_fmt.setForeground(QColor("#CE9178"))

        self.number_fmt = QTextCharFormat()
        self.number_fmt.setForeground(QColor("#B5CEA8"))

        self.comment_fmt = QTextCharFormat()
        self.comment_fmt.setForeground(QColor("#6A9955"))

    def highlightBlock(self, text):
        import re
        # Keywords
        for kw in self.KEYWORDS:
            pattern = rf"\b{kw}\b"
            for m in re.finditer(pattern, text, re.IGNORECASE):
                self.setFormat(m.start(), m.end() - m.start(), self.keyword_fmt)
        # Strings
        for m in re.finditer(r"'[^']*'", text):
            self.setFormat(m.start(), m.end() - m.start(), self.string_fmt)
        # Numbers
        for m in re.finditer(r"\b\d+\.?\d*\b", text):
            self.setFormat(m.start(), m.end() - m.start(), self.number_fmt)
        # Comments
        for m in re.finditer(r"--.*$", text):
            self.setFormat(m.start(), m.end() - m.start(), self.comment_fmt)


class ChatBubble(QFrame):
    """A chat message bubble."""

    def __init__(self, text: str, is_user: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        if is_user:
            self.setStyleSheet("""
                ChatBubble {
                    background-color: #2B5278;
                    border-radius: 10px;
                    padding: 8px;
                    margin: 4px 40px 4px 80px;
                }
            """)
        else:
            self.setStyleSheet("""
                ChatBubble {
                    background-color: #2D2D30;
                    border-radius: 10px;
                    padding: 8px;
                    margin: 4px 80px 4px 40px;
                }
            """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet("color: #D4D4D4; font-size: 13px;")
        layout.addWidget(label)


class SQLBlock(QFrame):
    """A syntax-highlighted SQL code block."""

    def __init__(self, sql: str, explanation: str = "", parent=None):
        super().__init__(parent)
        self.sql = sql
        self.setStyleSheet("""
            SQLBlock {
                background-color: #1E1E1E;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                margin: 4px 40px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        if explanation:
            exp_label = QLabel(explanation)
            exp_label.setWordWrap(True)
            exp_label.setStyleSheet("color: #9CDCFE; font-size: 12px; margin-bottom: 4px;")
            layout.addWidget(exp_label)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(sql)
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 11))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
            }
        """)
        # Size to content
        doc = self.text_edit.document()
        doc.setDefaultFont(QFont("Consolas", 11))
        height = int(doc.size().height()) + 20
        self.text_edit.setFixedHeight(min(height, 300))

        self.highlighter = SQLHighlighter(self.text_edit.document())
        layout.addWidget(self.text_edit)


class ResultTable(QFrame):
    """A data table widget for query results with export buttons."""

    export_excel = pyqtSignal()
    export_clipboard = pyqtSignal()
    open_excel = pyqtSignal()

    def __init__(self, columns: list, rows: list, max_display: int = 500, parent=None):
        super().__init__(parent)
        self.columns = columns
        self.rows = rows
        self.setStyleSheet("""
            ResultTable {
                background-color: #1E1E1E;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                margin: 4px 40px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Button bar
        btn_layout = QHBoxLayout()
        info_label = QLabel(f"{len(rows)} rows, {len(columns)} columns")
        info_label.setStyleSheet("color: #808080; font-size: 11px;")
        btn_layout.addWidget(info_label)
        btn_layout.addStretch()

        btn_style = """
            QPushButton {
                background-color: #0E639C;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #1177BB; }
        """

        copy_btn = QPushButton("Copy")
        copy_btn.setStyleSheet(btn_style)
        copy_btn.clicked.connect(self.export_clipboard.emit)
        btn_layout.addWidget(copy_btn)

        excel_btn = QPushButton("Save as Excel")
        excel_btn.setStyleSheet(btn_style)
        excel_btn.clicked.connect(self.export_excel.emit)
        btn_layout.addWidget(excel_btn)

        open_btn = QPushButton("Open in Excel")
        open_btn.setStyleSheet(btn_style)
        open_btn.clicked.connect(self.open_excel.emit)
        btn_layout.addWidget(open_btn)

        layout.addLayout(btn_layout)

        # Table
        display_rows = rows[:max_display]
        table = QTableWidget(len(display_rows), len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setMaximumSectionSize(300)
        table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #D4D4D4;
                gridline-color: #3C3C3C;
                border: none;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #2D2D30;
                color: #D4D4D4;
                padding: 4px;
                border: 1px solid #3C3C3C;
                font-weight: bold;
            }
        """)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)

        for r, row in enumerate(display_rows):
            for c, val in enumerate(row):
                text = str(val) if val is not None else ""
                item = QTableWidgetItem(text)
                if val is not None:
                    try:
                        float(val)
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    except (ValueError, TypeError):
                        pass
                table.setItem(r, c, item)

        table.setMaximumHeight(min(len(display_rows) * 28 + 40, 400))
        layout.addWidget(table)

        if len(rows) > max_display:
            trunc = QLabel(f"Showing {max_display} of {len(rows)} rows. Export to see all.")
            trunc.setStyleSheet("color: #808080; font-size: 11px;")
            layout.addWidget(trunc)


class WarningBanner(QFrame):
    """A warning banner for reasonability check results."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            WarningBanner {
                background-color: #3E2C00;
                border: 1px solid #6D5600;
                border-radius: 6px;
                margin: 4px 40px;
                padding: 8px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #FFD700; font-size: 12px;")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)


class ToolCallIndicator(QFrame):
    """Small indicator showing the bot is calling a tool."""

    def __init__(self, tool_name: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            ToolCallIndicator {
                background-color: #1A1A2E;
                border-left: 3px solid #0E639C;
                margin: 2px 40px 2px 50px;
                padding: 4px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        label = QLabel(f"Calling: {tool_name}")
        label.setStyleSheet("color: #808080; font-size: 11px; font-style: italic;")
        layout.addWidget(label)


class ImageWidget(QFrame):
    """Displays an image inline in the chat with an open button."""

    open_file = pyqtSignal(str)

    def __init__(self, image_path: str, caption: str = "", max_width: int = 700, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.setStyleSheet("""
            ImageWidget {
                background-color: #1E1E1E;
                border: 1px solid #3C3C3C;
                border-radius: 6px;
                margin: 4px 40px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Load and display image
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            if pixmap.width() > max_width:
                pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)
            img_label = QLabel()
            img_label.setPixmap(pixmap)
            img_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(img_label)
        else:
            err_label = QLabel(f"Could not load image: {image_path}")
            err_label.setStyleSheet("color: #FF6B6B;")
            layout.addWidget(err_label)

        # Caption and buttons
        btn_layout = QHBoxLayout()
        if caption:
            cap_label = QLabel(caption)
            cap_label.setStyleSheet("color: #808080; font-size: 11px;")
            btn_layout.addWidget(cap_label)
        btn_layout.addStretch()

        open_btn = QPushButton("Open")
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #0E639C; color: white; border: none;
                border-radius: 4px; padding: 4px 12px; font-size: 11px;
            }
            QPushButton:hover { background-color: #1177BB; }
        """)
        open_btn.clicked.connect(lambda: self.open_file.emit(self.image_path))
        btn_layout.addWidget(open_btn)

        layout.addLayout(btn_layout)
