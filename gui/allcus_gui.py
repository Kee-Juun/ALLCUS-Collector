"""
GUI Module for ALLCUS RPA
PyQt5 GUI with modern Instagram-like design
"""

import sys
import os
import shutil
import time
import re
from pathlib import Path
from datetime import date
from typing import Optional
from PyQt5.QtCore import Qt, QPoint, QModelIndex, QRect, QRectF, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap, QPalette, QBrush, QFontDatabase, QMouseEvent, QKeySequence, QColor, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDateEdit, QComboBox, QMessageBox, QCheckBox, QRadioButton,
    QCalendarWidget, QStyleFactory, QDialog, QLineEdit, QFrame, QShortcut, QPlainTextEdit,
    QStyledItemDelegate, QHeaderView, QTableView, QGraphicsDropShadowEffect
)
# Import our modules
from utils.allcus_prep import create_directory_structure, get_downloads_path
from gui.allcus_gui_progbar import RoundedProgressBar


def resource_path(relative_name: str) -> Path:
    """Get absolute path to bundled or local resource."""
    if hasattr(sys, "_MEIPASS"):
        # Running from bundled executable
        base_path = Path(sys._MEIPASS)
    else:
        # Running from source
        base_path = Path(__file__).parent.parent
    return base_path / "resources" / relative_name


class CalendarHeaderView(QHeaderView):
    """Custom header view for calendar with colored weekday headers"""
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
    
    def paintSection(self, painter, rect, logicalIndex):
        """Override to paint weekday headers with custom colors"""
        # Get the text for this section
        text = self.model().headerData(logicalIndex, self.orientation(), Qt.DisplayRole)
        
        # Save painter state
        painter.save()
        
        # Set bold font
        font = self.font()
        font.setBold(True)
        painter.setFont(font)
        
        # Set color based on day (Sunday=0, Monday=1, ..., Saturday=6)
        if logicalIndex == 0 or logicalIndex == 6:  # Sunday or Saturday - red
            painter.setPen(QColor("#FD1D1D"))  # Red color
        elif logicalIndex >= 1 and logicalIndex <= 5:  # Monday to Friday - purple
            painter.setPen(QColor("#833AB4"))  # Purple color
        else:
            painter.setPen(QColor("#ffffff"))  # Default white
        
        # Draw text centered
        painter.drawText(rect, Qt.AlignCenter, str(text) if text else "")
        
        painter.restore()


class CalendarHeaderDelegate(QStyledItemDelegate):
    """Custom delegate to style weekday headers with colors"""
    
    def paint(self, painter, option, index):
        """Paint header cells with special styling:
        - Sunday (column 0): red, bold
        - Monday-Friday (columns 1-5): purple, bold
        - Saturday (column 6): red, bold
        """
        col = index.column()
        # Save current state
        painter.save()
        
        # Fill background first
        painter.fillRect(option.rect, QColor("#1f1f2e"))
        
        # Set bold font
        font = option.font
        font.setBold(True)
        font.setPointSize(11)
        painter.setFont(font)
        
        # Set color based on day
        if col == 0 or col == 6:  # Sunday or Saturday - red
            painter.setPen(QColor("#FD1D1D"))  # Red color
        elif col >= 1 and col <= 5:  # Monday to Friday - purple
            painter.setPen(QColor("#833AB4"))  # Purple color - bright and visible
        else:
            painter.setPen(QColor("#ffffff"))  # Default white
        
        # Draw text
        text = index.data(Qt.DisplayRole)
        if text:
            painter.drawText(option.rect, Qt.AlignCenter, str(text))
        else:
            # Fallback: try to get text from model directly
            model = index.model()
            if model:
                text = model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
                if text:
                    painter.drawText(option.rect, Qt.AlignCenter, str(text))
        
        painter.restore()


class CustomCalendarWidget(QCalendarWidget):
    """Custom calendar widget with styled weekday headers"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.setFirstDayOfWeek(Qt.Sunday)  # Start from Sunday


class CalendarDialog(QDialog):
    """Google-style calendar dialog"""
    
    def __init__(self, parent=None, initial_date=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.selected_date = initial_date if initial_date else date.today()
        self.setup_ui()
        self.apply_google_style()
        # Close on escape key
        QShortcut(QKeySequence("Escape"), self, self.reject)
    
    def setup_ui(self):
        """Setup calendar dialog UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)
        
        # Calendar widget (using custom widget)
        self.calendar = CustomCalendarWidget()
        
        # Set initial date
        from PyQt5.QtCore import QDate
        qdate = QDate(self.selected_date.year, self.selected_date.month, self.selected_date.day)
        self.calendar.setSelectedDate(qdate)
        self.calendar.setCurrentPage(qdate.year(), qdate.month())
        
        # Make navigation arrows visible by removing icons and setting text
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QToolButton
        def set_arrow_text():
            # Find all tool buttons in the calendar
            for btn in self.calendar.findChildren(QToolButton):
                obj_name = btn.objectName()
                # Remove icon first
                btn.setIcon(QIcon())  # Clear the icon
                if "prevmonth" in obj_name or "previous" in obj_name.lower():
                    btn.setText("◀")
                    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)  # Show text only, no icon
                    btn.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; background: transparent; border: none;")
                elif "nextmonth" in obj_name or "next" in obj_name.lower():
                    btn.setText("▶")
                    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)  # Show text only, no icon
                    btn.setStyleSheet("color: #ffffff; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        # Try multiple times to catch buttons after they're created
        QTimer.singleShot(50, set_arrow_text)
        QTimer.singleShot(150, set_arrow_text)
        QTimer.singleShot(300, set_arrow_text)
        QTimer.singleShot(500, set_arrow_text)  # One more attempt
        
        # Connect selection
        self.calendar.selectionChanged.connect(self.on_date_selected)
        
        layout.addWidget(self.calendar)
    
    def apply_google_style(self):
        """Apply dark mode calendar styling matching ALLCUS theme"""
        self.setStyleSheet("""
        QDialog {
            background: #1f1f2e;
            border: 1px solid rgba(255, 255, 255, 0.25);
            border-radius: 16px;
        }
        QCalendarWidget {
            background: #1f1f2e;
            color: #ffffff;
            border: none;
        }
        QCalendarWidget QWidget#qt_calendar_navigationbar {
            background: rgba(0, 0, 0, 0.3);
            border: none;
            border-top-left-radius: 16px;
            border-top-right-radius: 16px;
            padding: 8px;
        }
        QCalendarWidget QToolButton {
            color: #ffffff;
            background: transparent;
            border: none;
            font-weight: 600;
            font-size: 16px;
            padding: 6px 10px;
            border-radius: 10px;
        }
        QCalendarWidget QToolButton:hover {
            background: rgba(255, 255, 255, 0.12);
            color: #ffffff;
        }
        QCalendarWidget QToolButton#qt_calendar_prevmonth {
            color: #ffffff;
        }
        QCalendarWidget QToolButton#qt_calendar_nextmonth {
            color: #ffffff;
        }
        QCalendarWidget QMenu {
            background: #1f1f2e;
            border: 1px solid rgba(255, 255, 255, 0.25);
            border-radius: 12px;
            padding: 4px;
            color: #ffffff;
        }
        QCalendarWidget QMenu::item {
            background: transparent;
            color: #ffffff;
            padding: 8px 20px;
            border-radius: 6px;
        }
        QCalendarWidget QMenu::item:selected {
            background: rgba(255, 255, 255, 0.15);
            color: #ffffff;
        }
        QCalendarWidget QMenu::item:hover {
            background: rgba(255, 255, 255, 0.20);
            color: #ffffff;
        }
        QCalendarWidget QSpinBox {
            border: 1px solid rgba(255, 255, 255, 0.25);
            border-radius: 10px;
            padding: 4px 8px;
            background: rgba(255, 255, 255, 0.1);
            color: #ffffff;
        }
        QCalendarWidget QAbstractItemView {
            selection-background-color: transparent;
            selection-color: #ffffff;
            outline: 0;
            border: none;
            background: #1f1f2e;
        }
        QCalendarWidget QAbstractItemView::item {
            padding: 6px;
            border-radius: 8px;
            color: #ffffff;
        }
        QCalendarWidget QAbstractItemView::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #833AB4, stop:1 #FD1D1D);
            color: #ffffff;
            font-weight: 600;
        }
        QCalendarWidget QAbstractItemView::item:hover {
            background: rgba(255, 255, 255, 0.10);
        }
        QCalendarWidget QHeaderView::section {
            background: #1f1f2e;
            color: #833AB4;
            font-weight: 700;
            font-size: 12px;
            padding: 8px 0px;
            border: none;
        }
        """)
    
    def on_date_selected(self):
        """Handle date selection"""
        qdate = self.calendar.selectedDate()
        self.selected_date = date(qdate.year(), qdate.month(), qdate.day())
        self.accept()
    
    def get_date(self):
        """Get selected date"""
        return self.selected_date


class CustomMessageBox(QDialog):
    """Custom styled message box matching the main GUI aesthetic"""

    def __init__(
        self,
        title: str,
        message: str,
        buttons,
        parent=None,
        default_button=None,
        details_title: Optional[str] = None,
        details_text: Optional[str] = None,
        button_text_overrides: Optional[dict] = None,
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(True)
        self._result = default_button if default_button is not None else QMessageBox.Ok

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title bar
        title_bar = QWidget()
        title_bar.setObjectName("dialogTitleBar")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(12, 6, 8, 6)
        title_layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("dialogTitleLabel")
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setObjectName("dialogCloseButton")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self._handle_close)
        title_layout.addWidget(close_btn)
        main_layout.addWidget(title_bar)

        # Content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(14)

        message_label = QLabel(message)
        message_label.setObjectName("dialogMessageLabel")
        message_label.setWordWrap(True)
        message_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(message_label)

        if details_text:
            details_label = QLabel(details_title or "")
            details_label.setObjectName("dialogDetailsLabel")
            details_label.setAlignment(Qt.AlignCenter)
            content_layout.addWidget(details_label)

            details_area = QLabel(details_text)
            details_area.setObjectName("dialogDetailsArea")
            details_area.setWordWrap(True)
            details_area.setAlignment(Qt.AlignCenter)
            details_area.setTextInteractionFlags(Qt.TextSelectableByMouse)
            content_layout.addWidget(details_area)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        for btn in self._buttons_from_mask(buttons, button_text_overrides):
            button = QPushButton(btn["text"])
            button.setObjectName(btn["object_name"])
            button.clicked.connect(lambda _, b=btn["value"]: self._handle_button(b))
            buttons_layout.addWidget(button)

        content_layout.addLayout(buttons_layout)
        main_layout.addWidget(content)

        self.setStyleSheet("""
            QDialog {
                background: rgba(20, 25, 35, 0.98);
                border: 2px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
            }
            QWidget#dialogTitleBar {
                background: rgba(255, 255, 255, 0.06);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QLabel#dialogTitleLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: bold;
            }
            QLabel#dialogMessageLabel {
                color: #ffffff;
                font-size: 13px;
            }
            QLabel#dialogDetailsLabel {
                color: #ffffff;
                font-size: 12px;
                font-weight: bold;
            }
            QLabel#dialogDetailsArea {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: #ffffff;
                font-size: 12px;
                padding: 6px;
            }
            QPushButton#dialogCloseButton {
                background: transparent;
                color: #ffffff;
                border: none;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton#dialogCloseButton:hover {
                color: #ff6b6b;
            }
            QPushButton#dialogPrimaryButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #833AB4, stop:1 #FD1D1D);
                border: none;
                border-radius: 10px;
                padding: 8px 18px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#dialogPrimaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #9B4CD9, stop:1 #FF3D3D);
            }
            QPushButton#dialogSecondaryButton {
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 10px;
                padding: 8px 18px;
                color: #ffffff;
            }
            QPushButton#dialogSecondaryButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
        """)

    @staticmethod
    def _buttons_from_mask(mask, text_overrides: Optional[dict] = None):
        order = [
            QMessageBox.Yes,
            QMessageBox.No,
            QMessageBox.Ok,
            QMessageBox.Cancel,
        ]
        mapping = {
            QMessageBox.Yes: {"text": "Yes", "value": QMessageBox.Yes, "object_name": "dialogPrimaryButton"},
            QMessageBox.No: {"text": "No", "value": QMessageBox.No, "object_name": "dialogSecondaryButton"},
            QMessageBox.Ok: {"text": "OK", "value": QMessageBox.Ok, "object_name": "dialogPrimaryButton"},
            QMessageBox.Cancel: {"text": "Cancel", "value": QMessageBox.Cancel, "object_name": "dialogSecondaryButton"},
        }
        if text_overrides:
            for key, value in text_overrides.items():
                if key in mapping and value:
                    mapping[key]["text"] = value
        return [mapping[b] for b in order if mask & b]

    def _handle_button(self, result):
        self._result = result
        self.accept()

    def _handle_close(self):
        self.accept()

    @staticmethod
    def information(
        parent,
        title,
        message,
        buttons=QMessageBox.Ok,
        details_title: Optional[str] = None,
        details_text: Optional[str] = None,
        button_text_overrides: Optional[dict] = None,
    ):
        dialog = CustomMessageBox(
            title, message, buttons, parent, default_button=QMessageBox.Ok,
            details_title=details_title, details_text=details_text,
            button_text_overrides=button_text_overrides,
        )
        dialog.exec_()
        return dialog._result

    @staticmethod
    def warning(
        parent,
        title,
        message,
        buttons=QMessageBox.Ok,
        details_title: Optional[str] = None,
        details_text: Optional[str] = None,
        button_text_overrides: Optional[dict] = None,
    ):
        dialog = CustomMessageBox(
            title, message, buttons, parent, default_button=QMessageBox.Ok,
            details_title=details_title, details_text=details_text,
            button_text_overrides=button_text_overrides,
        )
        dialog.exec_()
        return dialog._result

    @staticmethod
    def critical(
        parent,
        title,
        message,
        buttons=QMessageBox.Ok,
        details_title: Optional[str] = None,
        details_text: Optional[str] = None,
        button_text_overrides: Optional[dict] = None,
    ):
        dialog = CustomMessageBox(
            title, message, buttons, parent, default_button=QMessageBox.Ok,
            details_title=details_title, details_text=details_text,
            button_text_overrides=button_text_overrides,
        )
        dialog.exec_()
        return dialog._result

    @staticmethod
    def question(
        parent,
        title,
        message,
        buttons=QMessageBox.Yes | QMessageBox.No,
        default_button=QMessageBox.No,
        details_title: Optional[str] = None,
        details_text: Optional[str] = None,
        button_text_overrides: Optional[dict] = None,
    ):
        dialog = CustomMessageBox(
            title, message, buttons, parent, default_button=default_button,
            details_title=details_title, details_text=details_text,
            button_text_overrides=button_text_overrides,
        )
        dialog.exec_()
        return dialog._result


class DatePickerEdit(QWidget):
    """Custom date picker that opens Google-style calendar dialog"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_date = date.today()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup date picker UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Date input field
        self.date_input = QLineEdit()
        self.date_input.setReadOnly(True)
        self.date_input.setMinimumHeight(35)
        self.update_display()
        layout.addWidget(self.date_input)
        
        # Calendar button
        self.calendar_btn = QPushButton()
        self.calendar_btn.setFixedSize(35, 35)
        self.calendar_btn.setObjectName("calendarButton")
        self.calendar_btn.clicked.connect(self.show_calendar)
        
        # Set calendar icon programmatically
        try:
            script_dir = Path(__file__).parent.parent.resolve()
            icon_path = script_dir / "resources" / "calendar_icon.png"
            if icon_path.exists():
                icon = QIcon(str(icon_path))
                self.calendar_btn.setIcon(icon)
                # Set icon size directly using QSize
                from PyQt5.QtCore import QSize
                self.calendar_btn.setIconSize(QSize(20, 20))
        except Exception as e:
            print(f"Warning: Could not load calendar icon: {str(e)}")
        
        layout.addWidget(self.calendar_btn)
    
    def update_display(self):
        """Update the displayed date"""
        if hasattr(self, '_display_format'):
            # Use custom format if set
            fmt = self._display_format.replace('MM', '%m').replace('dd', '%d').replace('yyyy', '%Y')
            self.date_input.setText(self.current_date.strftime(fmt))
        else:
            self.date_input.setText(self.current_date.strftime("%m/%d/%Y"))
    
    def show_calendar(self):
        """Show calendar dialog positioned near the button"""
        dialog = CalendarDialog(self, self.current_date)
        # Position dialog below the calendar button
        button_pos = self.calendar_btn.mapToGlobal(self.calendar_btn.rect().bottomLeft())
        dialog.move(button_pos.x() - 150, button_pos.y() + 5)  # Offset to align nicely
        if dialog.exec_() == QDialog.Accepted:
            self.current_date = dialog.get_date()
            self.update_display()
    
    def date(self):
        """Get current date (QDate-like interface)"""
        from PyQt5.QtCore import QDate
        return QDate(self.current_date.year, self.current_date.month, self.current_date.day)
    
    def setDate(self, qdate):
        """Set date (QDate-like interface)"""
        from PyQt5.QtCore import QDate
        if isinstance(qdate, QDate):
            self.current_date = date(qdate.year(), qdate.month(), qdate.day())
        elif isinstance(qdate, date):
            self.current_date = qdate
        elif hasattr(qdate, 'year') and hasattr(qdate, 'month') and hasattr(qdate, 'day'):
            # Handle date.today() or similar
            self.current_date = date(qdate.year, qdate.month, qdate.day)
        self.update_display()
    
    def setDisplayFormat(self, fmt):
        """Set display format (for compatibility)"""
        self._display_format = fmt
        self.update_display()
    
    def setMinimumHeight(self, height):
        """Set minimum height"""
        super().setMinimumHeight(height)
        self.date_input.setMinimumHeight(height)
        self.calendar_btn.setFixedSize(height, height)


class CourtHeaderLabel(QLabel):
    """Clickable header label that cycles court selection."""

    selection_changed = pyqtSignal(str)
    rapid_click_detected = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._states = ["ALLCUS", "ALLCUS HQ", "ALLCUS NY"]
        self._index = 0
        self.setText(self._states[self._index])
        self.setCursor(Qt.PointingHandCursor)
        self._last_click_ts = 0.0
        self._rapid_click_threshold = 0.35

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            now = time.monotonic()
            if self._last_click_ts and (now - self._last_click_ts) < self._rapid_click_threshold:
                self.rapid_click_detected.emit(now - self._last_click_ts)
                self._last_click_ts = now
            self._last_click_ts = now
            # Toggle between HQ and NY after initial ALLCUS state
            if self._index == 0:
                self._index = 1
            else:
                self._index = 2 if self._index == 1 else 1
            self.setText(self._states[self._index])
            self.selection_changed.emit(self._states[self._index])
        super().mousePressEvent(event)

    def is_court_selected(self) -> bool:
        return self._index != 0

    def get_selected_court(self) -> Optional[str]:
        if self._index == 2:
            return "ALLCUS_NY"
        if self._index == 1:
            return "ALLCUS_HQ"
        return None


class TitleBar(QWidget):
    """Custom title bar widget with minimize and close buttons"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self._drag_position = QPoint()
        self.setup_ui()
    
    def setup_ui(self):
        """Setup title bar UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 0, 10, 0)
        layout.setSpacing(10)
        
        # Title label
        title_label = QLabel("ALLCUS Document Collector")
        title_label.setObjectName("titleLabel")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(11)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        layout.addStretch()  # Push buttons to the right
        
        # Minimize button
        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("minimizeButton")
        minimize_btn.setFixedSize(32, 32)
        minimize_btn.setToolTip("Minimize")
        minimize_btn.clicked.connect(self.parent_window.showMinimized if self.parent_window else lambda: None)
        layout.addWidget(minimize_btn)
        
        # Close button
        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeButton")
        close_btn.setFixedSize(32, 32)
        close_btn.setToolTip("Close")
        close_btn.clicked.connect(self.parent_window.close if self.parent_window else lambda: None)
        layout.addWidget(close_btn)
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for window dragging"""
        if event.button() == Qt.LeftButton:
            if self.parent_window:
                self._drag_position = event.globalPos() - self.parent_window.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for window dragging"""
        if event.buttons() == Qt.LeftButton and not self._drag_position.isNull():
            if self.parent_window:
                self.parent_window.move(event.globalPos() - self._drag_position)
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release"""
        self._drag_position = QPoint()
        event.accept()


def main():
    """Main entry point for GUI"""
    app = QApplication(sys.argv)
    # Use Fusion style so Qt style sheets fully control widgets (including calendars)
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    icon_path = resource_path("allcus_icon_premium.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    from .allcus_gui_window import ALLCUSWindow
    window = ALLCUSWindow()
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    sys.exit(app.exec_())

