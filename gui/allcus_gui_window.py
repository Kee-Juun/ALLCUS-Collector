import os
import re
import shutil
import time
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap, QPalette, QBrush, QColor, QFontDatabase
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox,
    QRadioButton, QFrame, QGraphicsDropShadowEffect, QMainWindow
)

from utils.allcus_prep import create_directory_structure, get_downloads_path
from gui.allcus_gui_autowork import AutomationWorker
from gui.allcus_gui import TitleBar, CourtHeaderLabel, DatePickerEdit, CustomMessageBox
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


class ALLCUSWindow(QMainWindow):
    """Main GUI window for ALLCUS RPA"""
    
    def __init__(self):
        super().__init__()
        # Set frameless window hint for custom title bar
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.worker: Optional[AutomationWorker] = None
        self.run_folder: Optional[Path] = None
        self.base_folder: Optional[Path] = None
        self._is_cancelling = False  # Track if we're in the process of cancelling
        self._close_after_cancel = False  # Close only after the worker thread has stopped
        self._in_prep_stage = False  # Suppress prep-stage status noise
        self._in_duplicate_stage = False  # Suppress duplicate-check noise
        self._rapid_click_count = 0
        self._rapid_click_stage = 0
        self._last_rapid_click_ts = 0.0
        self.setup_ui()
        self.set_background_image()
        self.apply_modern_theme()
    
    def setup_ui(self):
        """Setup the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Custom title bar
        self.title_bar = TitleBar(self)
        self.title_bar.setFixedHeight(40)
        self.title_bar.setObjectName("titleBar")
        
        # Add title bar to main layout
        main_layout.addWidget(self.title_bar)
        
        # Content widget (everything else)
        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(30, 30, 30, 30)
        
        # Header (also acts as court selector)
        header_label = CourtHeaderLabel()
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setObjectName("headerLabel")
        self.header_label = header_label
        self.header_label.selection_changed.connect(self.on_court_selection_changed)
        self.header_label.rapid_click_detected.connect(self.on_court_selection_rapid_click)

        # Load custom header font (Boldfinger) with graceful fallback
        header_font = QFont()
        try:
            font_path = resource_path("Boldfinger.ttf")
            if font_path.exists():
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                if font_id != -1:
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    if families:
                        header_font = QFont(families[0], 48)
            # Fallback if font missing or load failed
            if header_font.family() == "":
                header_font.setPointSize(48)
                header_font.setBold(True)
        except Exception:
            header_font.setPointSize(48)
            header_font.setBold(True)

        header_label.setFont(header_font)
        # Subtle shadow to add depth to header text
        header_shadow = QGraphicsDropShadowEffect(self)
        header_shadow.setBlurRadius(18)
        header_shadow.setOffset(0, 3)
        header_shadow.setColor(QColor(0, 0, 0, 160))
        header_label.setGraphicsEffect(header_shadow)
        content_layout.addWidget(header_label)
        
        # Label font used for other labels
        label_font = QFont()
        label_font.setBold(True)
        
        # Date selection
        date_layout = QHBoxLayout()
        date_layout.setSpacing(15)  # Spacing between start and end date sections
        
        # Start date (default to one month ago)
        start_layout = QVBoxLayout()
        start_layout.setSpacing(5)  # Small spacing between label and input
        start_label = QLabel("Start Date:")
        start_label.setFont(label_font)
        self.start_date_edit = DatePickerEdit()
        # Calculate one month ago
        from datetime import timedelta
        today = date.today()
        # Subtract approximately three months (90 days)
        one_month_ago = today - timedelta(days=90)
        self.start_date_edit.setDate(one_month_ago)
        self.start_date_edit.setMinimumHeight(35)
        self.start_date_edit.setDisplayFormat("MM/dd/yyyy")
        start_layout.addWidget(start_label)
        start_layout.addWidget(self.start_date_edit)
        
        # End date (default to today)
        end_layout = QVBoxLayout()
        end_layout.setSpacing(5)  # Small spacing between label and input
        end_label = QLabel("End Date:")
        end_label.setFont(label_font)
        self.end_date_edit = DatePickerEdit()
        self.end_date_edit.setDate(date.today())
        self.end_date_edit.setMinimumHeight(35)
        self.end_date_edit.setDisplayFormat("MM/dd/yyyy")
        end_layout.addWidget(end_label)
        end_layout.addWidget(self.end_date_edit)
        
        date_layout.addLayout(start_layout)
        date_layout.addLayout(end_layout)
        content_layout.addLayout(date_layout)
        
        # Headless mode toggle
        self.headless_radio = QRadioButton("Headless Mode")
        self.headless_radio.setFont(label_font)
        self.headless_radio.setChecked(True)  # Default to headless
        self.headless_radio.setMinimumHeight(30)
        content_layout.addWidget(self.headless_radio)
        
        # Buttons layout
        buttons_layout = QHBoxLayout()
        
        # Run button
        self.run_button = QPushButton("Run")
        self.run_button.setMinimumHeight(45)
        # Force pill-shaped style for this specific button
        self.run_button.setStyleSheet("border-radius: 22px; padding: 12px 36px;")
        run_shadow = QGraphicsDropShadowEffect(self)
        run_shadow.setBlurRadius(14)
        run_shadow.setOffset(0, 3)
        run_shadow.setColor(QColor(0, 0, 0, 140))
        self.run_button.setGraphicsEffect(run_shadow)
        self.run_button.clicked.connect(self.on_run_clicked)
        buttons_layout.addWidget(self.run_button)
        
        # View Folder button
        self.view_folder_button = QPushButton("View Folder")
        self.view_folder_button.setMinimumHeight(45)
        # Force pill-shaped style for this specific button
        self.view_folder_button.setStyleSheet("border-radius: 22px; padding: 12px 36px;")
        view_shadow = QGraphicsDropShadowEffect(self)
        view_shadow.setBlurRadius(14)
        view_shadow.setOffset(0, 3)
        view_shadow.setColor(QColor(0, 0, 0, 140))
        self.view_folder_button.setGraphicsEffect(view_shadow)
        self.view_folder_button.clicked.connect(self.on_view_folder_clicked)
        buttons_layout.addWidget(self.view_folder_button)
        
        content_layout.addLayout(buttons_layout)
        
        # Progress bar (using custom rounded progress bar)
        self.progress_bar = RoundedProgressBar()
        self.progress_bar.setMinimumHeight(30)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        content_layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(30)
        content_layout.addWidget(self.status_label)
        
        # Add content widget to main layout
        main_layout.addWidget(content_widget)
        
        # Set window properties
        self.setWindowTitle("ALLCUS Document Collector")
        self.setGeometry(300, 150, 600, 500)
        
        # Require court selection before enabling controls
        self.update_controls_for_court_selection()
    
    def set_background_image(self):
        """Set background image for the main window using QPalette"""
        try:
            gui_bg_path = resource_path("gui_bg.png")
            
            if gui_bg_path.exists():
                pixmap = QPixmap(str(gui_bg_path))
                if not pixmap.isNull():
                    # Scale pixmap to window size (cover mode)
                    scaled_pixmap = pixmap.scaled(
                        self.size(), 
                        Qt.KeepAspectRatioByExpanding, 
                        Qt.SmoothTransformation
                    )
                    # Create QBrush from QPixmap
                    brush = QBrush(scaled_pixmap)
                    palette = QPalette()
                    palette.setBrush(QPalette.Window, brush)
                    self.setPalette(palette)
        except Exception as e:
            print(f"Warning: Could not load background image: {str(e)}")
    
    def resizeEvent(self, event):
        """Handle window resize to update background image"""
        self.set_background_image()
        super().resizeEvent(event)
    
    
    def apply_modern_theme(self):
        """Apply modern Instagram-like theme"""
        # Get absolute paths to images for Qt stylesheet
        # Qt stylesheets require forward slashes and proper path format
        calendar_icon_path = resource_path("calendar_icon.png")
        gui_bg_path = resource_path("gui_bg.png")
        
        # Convert to forward slashes for Qt stylesheet
        calendar_icon_path_str = str(calendar_icon_path).replace('\\', '/')
        gui_bg_path_str = str(gui_bg_path).replace('\\', '/')
        
        # Build stylesheet (background image is set programmatically via QPalette)
        stylesheet = """
            QMainWindow {
                background: transparent;
            }
            QWidget {
                background: transparent;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
            }
            QLabel[objectName="headerLabel"] {
                font-family: 'Boldfinger', 'Segoe UI', Arial, sans-serif;
                font-size: 48pt;
                font-weight: bold;
                color: #ffffff;
            }
            QComboBox {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 10px;
                padding: 8px;
                color: #ffffff;
                font-size: 14px;
            }
            QComboBox:hover {
                background: rgba(255, 255, 255, 0.3);
                border: 2px solid rgba(255, 255, 255, 0.5);
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox QAbstractItemView {
                background: rgba(131, 58, 180, 0.95);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 10px;
                selection-background-color: rgba(255, 255, 255, 0.3);
                color: #ffffff;
            }
            QDateEdit {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 10px;
                padding: 8px;
                color: #ffffff;
                font-size: 14px;
            }
            QDateEdit:hover {
                background: rgba(255, 255, 255, 0.3);
                border: 2px solid rgba(255, 255, 255, 0.5);
            }
            QDateEdit::drop-down {
                border: none;
                width: 35px;
                height: 35px;
                image: url(""" + calendar_icon_path_str + """);
            }
            QDateEdit::drop-down:hover {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 5px;
            }
            /* Custom DatePickerEdit styling */
            DatePickerEdit QLineEdit {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-top-left-radius: 10px;
                border-bottom-left-radius: 10px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 8px;
                color: #ffffff;
                font-size: 14px;
            }
            DatePickerEdit QLineEdit:hover {
                background: rgba(255, 255, 255, 0.3);
                border: 2px solid rgba(255, 255, 255, 0.5);
            }
            QPushButton#calendarButton {
                background: rgba(255, 255, 255, 0.2);
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-left: none;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                image: url(""" + calendar_icon_path_str + """);
            }
            QPushButton#calendarButton:hover {
                background-color: rgba(255, 255, 255, 0.3);
                border: 2px solid rgba(255, 255, 255, 0.5);
                border-left: none;
            }
            QPushButton#calendarButton:pressed {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #833AB4, stop:1 #FD1D1D);
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #9B4CD9, stop:1 #FF3D3D);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #6B2A94, stop:1 #DD1D1D);
            }
            QPushButton:disabled {
                background: rgba(255, 255, 255, 0.2);
                color: rgba(255, 255, 255, 0.5);
            }
            QProgressBar {
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 15px;
                background: rgba(255, 255, 255, 0.1);
                text-align: center;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #833AB4, stop:1 #FD1D1D);
                border-radius: 13px;
                margin: 2px;
                border: none;
            }
            QProgressBar::chunk:first {
                border-top-left-radius: 13px;
                border-bottom-left-radius: 13px;
            }
            QProgressBar::chunk:only-one {
                border-radius: 13px;
            }
            QCheckBox {
                color: #ffffff;
                font-size: 14px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 5px;
                background: rgba(255, 255, 255, 0.1);
            }
            QCheckBox::indicator:hover {
                border: 2px solid rgba(255, 255, 255, 0.5);
                background: rgba(255, 255, 255, 0.2);
            }
            QCheckBox::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #833AB4, stop:1 #FD1D1D);
                border: 2px solid rgba(255, 255, 255, 0.5);
            }
            QRadioButton {
                color: #ffffff;
                font-size: 14px;
            }
            QRadioButton::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid rgba(255, 255, 255, 0.3);
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.1);
            }
            QRadioButton::indicator:hover {
                border: 2px solid rgba(255, 255, 255, 0.5);
                background: rgba(255, 255, 255, 0.2);
            }
            QRadioButton::indicator:checked {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #833AB4, stop:1 #FD1D1D);
                border: 2px solid rgba(255, 255, 255, 0.5);
            }
            QWidget#titleBar {
                background: rgba(0, 0, 0, 0.3);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            QLabel#titleLabel {
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton#minimizeButton, QPushButton#closeButton {
                background: transparent;
                border: none;
                border-radius: 5px;
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
                padding: 0;
                margin: 0;
            }
            QPushButton#minimizeButton:hover {
                background: rgba(255, 255, 255, 0.2);
            }
            QPushButton#closeButton:hover {
                background: rgba(255, 0, 0, 0.5);
            }
            QPushButton#minimizeButton:pressed, QPushButton#closeButton:pressed {
                background: rgba(255, 255, 255, 0.1);
            }
        """
        
        self.setStyleSheet(stylesheet)
    
    def update_status(self, message: str):
        """Update status message (extract just the log message part)"""
        # Extract message after logging level
        # Format: HH:MM:SS - DD/MM/YYYY - LEVEL - message
        match = re.search(r' - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - (.*)', message)
        if match:
            level = match.group(1)
            display_message = match.group(2)
        else:
            level = None
            display_message = message

        display_message = display_message.strip()

        # During prep stage, only show "Initializing Chrome browser" until extraction starts
        if self._in_prep_stage and level not in ("WARNING", "ERROR", "CRITICAL"):
            if "Extracting rulings from page 1" in display_message:
                self._in_prep_stage = False
            elif "Initializing Chrome browser" not in display_message:
                return

        # During duplicate check, keep the status broad and calm. The tracker
        # setup and comparison steps produce many internal log lines.
        duplicate_status = "Checking for duplicates..."
        if duplicate_status in display_message:
            self._in_duplicate_stage = True
        if self._in_duplicate_stage and level not in ("WARNING", "ERROR", "CRITICAL"):
            duplicate_done_markers = (
                "Downloading ",
                "No unique rulings found",
                "No valid docket numbers",
                "Converting PDFs",
                "Generating Excel report",
            )
            if any(marker in display_message for marker in duplicate_done_markers):
                self._in_duplicate_stage = False
            elif duplicate_status not in display_message:
                return
        
        # Truncate with ellipses
        if len(display_message) > 80:
            display_message = display_message[:77] + "..."
        
        self.status_label.setText(display_message)
        self.status_label.setToolTip(message)  # Full message in tooltip

    def update_progress(self, value: int, phase: str, processed: int, total: int):
        """Update progress bar in determinate mode for download/convert phases"""
        if phase in ("download", "convert"):
            if self.progress_bar.minimum() == 0 and self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
            value = max(0, min(100, value))
            self.progress_bar.setValue(value)
            if total > 0:
                if phase == "download":
                    self.status_label.setText(f"Downloading {processed}/{total} documents...")
                else:
                    self.status_label.setText(f"Converting {processed}/{total} documents...")

    def update_controls_for_court_selection(self):
        """Enable/disable controls based on court selection state."""
        court_selected = self.header_label.is_court_selected()
        self.run_button.setEnabled(court_selected)
        self.start_date_edit.setEnabled(court_selected)
        self.end_date_edit.setEnabled(court_selected)
        self.headless_radio.setEnabled(court_selected)

    def on_court_selection_changed(self, _label_text: str):
        """Handle court selection changes from the header."""
        if self.worker and self.worker.isRunning():
            return
        self.update_controls_for_court_selection()

    def on_court_selection_rapid_click(self, _delta_seconds: float):
        """Provide feedback when the court selector is clicked too quickly."""
        if self.worker and self.worker.isRunning():
            return
        now = time.monotonic()
        if self._last_rapid_click_ts and (now - self._last_rapid_click_ts) >= 3.0:
            self._rapid_click_stage = 0
            self._rapid_click_count = 0
        self._last_rapid_click_ts = now
        messages = [
            "Whoah! I'm getting dizzy. Please be gentle.",
            "I feel like I'm about to vomit.",
            "BLEGHHHH!!!",
            "MAKE IT STOPPP!!!",
            "What did I do to you? Why are you doing this to me?",
        ]
        self._rapid_click_count += 1
        apology_prompted = False
        if self._rapid_click_count >= 3:
            if self._rapid_click_stage < len(messages) - 1:
                self._rapid_click_stage += 1
                self._rapid_click_count = 1
            else:
                apology_prompted = True
                self._rapid_click_stage = 0
                self._rapid_click_count = 0

        if apology_prompted:
            CustomMessageBox.information(
                self,
                "Please Apologize",
                "ALLCUS Bot is upset with you and doesn't want to work anymore unless you apologize.\n"
                "Do you apologize?",
                QMessageBox.Ok,
                button_text_overrides={QMessageBox.Ok: "I'm Sorry"},
            )
            self.status_label.setText(
                "Okay, I forgive you. But why do I have a feeling you'll do it again?"
            )
            QTimer.singleShot(5000, lambda: self.status_label.setText("Ready"))
            return

        self.status_label.setText(messages[self._rapid_click_stage])
        QTimer.singleShot(1500, lambda: self.status_label.setText("Ready"))
    
    def delete_run_folder(self):
        """Delete the run folder if it exists (used when canceling)"""
        if self.run_folder and self.run_folder.exists():
            try:
                shutil.rmtree(self.run_folder)
            except Exception as e:
                # Log error but don't block - folder might be in use
                print(f"Warning: Could not delete run folder: {str(e)}")
    
    def on_run_clicked(self):
        """Handle run button click"""
        if self.worker and self.worker.isRunning():
            # Cancel current run
            self._is_cancelling = True
            self.worker.cancel()
            # Let the worker exit gracefully and clean up in on_automation_finished
            self.run_button.setEnabled(False)
            self.status_label.setText("Cancelling automation...")
            return
        
        # Get inputs
        court = self.header_label.get_selected_court()
        if not court:
            CustomMessageBox.information(
                self,
                "Select Court",
                "Please click the ALLCUS header to choose ALLCUS HQ or ALLCUS NY before starting."
            )
            return
        start_date = self.start_date_edit.date().toString("MM/dd/yyyy")
        end_date = self.end_date_edit.date().toString("MM/dd/yyyy")
        year = str(self.start_date_edit.date().year())
        
        # Validate dates
        if self.start_date_edit.date() > self.end_date_edit.date():
            CustomMessageBox.warning(self, "Invalid Dates", "Start date must be before end date.")
            return
        
        # Create directory structure
        try:
            self.base_folder, self.run_folder = create_directory_structure(court)
        except Exception as e:
            CustomMessageBox.critical(self, "Error", f"Failed to create directories: {str(e)}")
            return
        
        # Disable UI
        self.run_button.setText("Cancel")
        self.run_button.setEnabled(True)
        self.header_label.setEnabled(False)
        self.start_date_edit.setEnabled(False)
        self.end_date_edit.setEnabled(False)
        self.headless_radio.setEnabled(False)
        self.view_folder_button.setEnabled(False)
        self._in_prep_stage = True
        self._in_duplicate_stage = False
        # Set progress bar to indeterminate mode (animated)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("Starting automation...")
        
        # Get headless mode preference
        headless_mode = self.headless_radio.isChecked()
        
        # Start worker thread
        self.worker = AutomationWorker(court, start_date, end_date, year, self.run_folder, headless_mode)
        self.worker.log_signal.connect(self.update_status)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.on_automation_finished)
        self.worker.start()
    
    def open_folder(self, folder_path: Path):
        """Open a folder in the default file manager"""
        try:
            if sys.platform == "win32":
                os.startfile(str(folder_path))
            elif sys.platform == "darwin":  # macOS
                os.system(f"open '{folder_path}'")
            else:  # Linux and others
                os.system(f"xdg-open '{folder_path}'")
        except Exception as e:
            CustomMessageBox.warning(self, "Error", f"Failed to open folder: {str(e)}")
    
    def on_view_folder_clicked(self):
        """Handle View Folder button click"""
        # Get the base folder (ALLCUS Collections)
        downloads = get_downloads_path()
        base_folder = downloads / "ALLCUS Collections"
        
        if base_folder.exists():
            self.open_folder(base_folder)
        else:
            CustomMessageBox.information(
                self, "Folder Not Found",
                f"The ALLCUS Collections folder does not exist yet.\n\n"
                f"Expected location: {base_folder}\n\n"
                f"It will be created when you run an automation."
            )

    def _unavailable_download_notice(self) -> Optional[str]:
        count = 0
        if self.worker:
            count = getattr(self.worker, "unavailable_download_count", 0)
        if count <= 0:
            return None
        noun = "ruling" if count == 1 else "rulings"
        verb = "was" if count == 1 else "were"
        return f"{count} {noun} {verb} not available for Download."

    def _last_collection_details_text(self) -> Optional[str]:
        if not self.worker or not self.worker.last_duplicate_filename or not self.worker.last_duplicate_date:
            return None

        detail_lines = [self.worker.last_duplicate_filename]
        if self.worker.last_duplicate_sid:
            detail_lines.append(self.worker.last_duplicate_sid)
        detail_lines.append(self.worker.last_duplicate_date)
        return "\n".join(detail_lines)
    
    def on_automation_finished(self, success: bool, message: str):
        """Handle automation completion"""
        # Check if this was a cancellation
        was_cancelled = self._is_cancelling or (self.worker and getattr(self.worker, '_cancelled', False))
        self._in_prep_stage = False
        self._in_duplicate_stage = False
        
        # If cancelled, delete the run folder (may already be deleted, but safe to try again)
        if was_cancelled:
            should_close = self._close_after_cancel
            self.delete_run_folder()
            self._is_cancelling = False
            self.reset_ui()
            if should_close:
                self.status_label.setText("Automation cancelled. Closing...")
                QTimer.singleShot(50, self._close_when_worker_stopped)
                return
            self.status_label.setText("Automation cancelled. UI reset.")
            QTimer.singleShot(3000, lambda: self.status_label.setText("Ready"))
            return  # Don't show any dialogs if cancelled
        
        if success:
            # Show final status before reset
            self.status_label.setText("Done")
            QTimer.singleShot(1200, self.reset_ui)
            # Show success message and offer to open folder
            message_lines = []
            unavailable_notice = self._unavailable_download_notice()
            if unavailable_notice:
                message_lines.extend([unavailable_notice, ""])
            message_lines.extend([
                message,
                "",
                "Would you like to open the folder containing the documents, log, and report?"
            ])
            reply = CustomMessageBox.information(
                self, "Success", 
                "\n".join(message_lines),
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes and self.run_folder:
                self.open_folder(self.run_folder)
        else:
            self.reset_ui()
            # Handle specific error cases
            if message == "PAGE_LOAD_FAILED":
                reply = CustomMessageBox.question(
                    self, "Connection Error",
                    "Failed to load court site. Please check your VPN or Internet connection.\n\n"
                    "Click OK to try again, or Cancel to exit.",
                    QMessageBox.Ok | QMessageBox.Cancel
                )
                if reply == QMessageBox.Ok:
                    # Allow user to try again
                    pass
                else:
                    return
            elif message == "NO_RULINGS_FOUND":
                reply = CustomMessageBox.question(
                    self, "No Rulings Found",
                    "No rulings found for the selected date range.\n\n"
                    "Would you like to adjust the date range and try again?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    # User can adjust dates and click run again
                    pass
                else:
                    return
            elif message in ("No unique rulings found after duplicate check.", "NO_DOWNLOADS_AVAILABLE"):
                details_text = self._last_collection_details_text()
                message_lines = []
                unavailable_notice = self._unavailable_download_notice()
                if unavailable_notice:
                    message_lines.extend([unavailable_notice, ""])
                if message == "NO_DOWNLOADS_AVAILABLE":
                    message_lines.append("No documents were collected for the selected date range.")
                    message_lines.append("Check the log for full details.")
                else:
                    message_lines.append("All documents in the selected date range already exist in the database.")
                CustomMessageBox.information(
                    self, "No New Documents Collected",
                    "\n".join(message_lines),
                    details_title="Most Recent Collection:",
                    details_text=details_text
                )
            else:
                CustomMessageBox.critical(self, "Error", message)

        self._close_after_cancel = False
    
    def reset_ui(self):
        """Reset UI to initial state"""
        self.run_button.setText("Run")
        self.header_label.setEnabled(True)
        self.view_folder_button.setEnabled(True)
        self._in_prep_stage = False
        self._in_duplicate_stage = False
        self.update_controls_for_court_selection()
        # Stop progress bar animation by setting determinate range with 0 value
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready")
        if self.worker and getattr(self.worker, "logger", None):
            try:
                self.worker.logger.info("Ready")
            except Exception:
                pass

    def _close_when_worker_stopped(self):
        """Finish a user-requested close after cancellation has stopped the worker."""
        if self.worker and self.worker.isRunning():
            QTimer.singleShot(50, self._close_when_worker_stopped)
            return
        self._close_after_cancel = False
        self.close()
    
    def closeEvent(self, event):
        """Handle window close"""
        if self.worker and self.worker.isRunning():
            if self._close_after_cancel:
                event.ignore()
                return
            reply = CustomMessageBox.question(
                self, "Automation Running",
                "Automation is currently running. Do you want to cancel and exit?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._is_cancelling = True
                self._close_after_cancel = True
                self.worker.cancel()
                self.run_button.setEnabled(False)
                self.status_label.setText("Cancelling automation...")
                event.ignore()
            else:
                event.ignore()
        else:
            self._close_after_cancel = False
            event.accept()
