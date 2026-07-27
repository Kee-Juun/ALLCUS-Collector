"""
Logging Module for ALLCUS RPA
Handles all logging functionality with custom format
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


class ALLCUSLogger:
    """Custom logger for ALLCUS RPA with formatted output"""
    
    def __init__(self, run_folder: Path, log_signal=None):
        """
        Initialize logger
        
        Args:
            run_folder: Path to the run folder (e.g., HQ_03-27-56_01-05-2026)
            log_signal: Optional PyQt signal for GUI updates
        """
        self.run_folder = run_folder
        self.log_signal = log_signal
        
        # Create log filename: LOG_COURT_HH-MM-SS_MM-DD-YYYY.txt
        run_folder_name = run_folder.name
        log_filename = f"LOG_{run_folder_name}.txt"
        log_path = run_folder / log_filename
        
        # Set up logger
        self.logger = logging.getLogger("ALLCUS")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers.clear()
        
        # File handler
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Custom formatter: HH:MM:SS - DD/MM/YYYY - LOGGING LEVEL - Log message
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S - %d/%m/%Y'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        self.file_handler = file_handler
        self.console_handler = console_handler
    
    def _format_for_gui(self, level: str, message: str) -> str:
        return f"{datetime.now().strftime('%H:%M:%S - %d/%m/%Y')} - {level} - {message}"

    def _emit_to_gui(self, level: str, message: str):
        """Emit log message to GUI if signal is available"""
        if self.log_signal and level != "DEBUG":
            try:
                self.log_signal.emit(self._format_for_gui(level, message))
            except Exception:
                pass
    
    def debug(self, message: str):
        """Log debug message"""
        self.logger.debug(message)
        self._emit_to_gui("DEBUG", message)
    
    def info(self, message: str):
        """Log info message"""
        self.logger.info(message)
        self._emit_to_gui("INFO", message)
    
    def warning(self, message: str):
        """Log warning message"""
        self.logger.warning(message)
        self._emit_to_gui("WARNING", message)
    
    def error(self, message: str):
        """Log error message"""
        self.logger.error(message)
        self._emit_to_gui("ERROR", message)
    
    def critical(self, message: str):
        """Log critical message"""
        self.logger.critical(message)
        self._emit_to_gui("CRITICAL", message)
    
    def close(self):
        """Close logger handlers"""
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
        self.file_handler = None
        self.console_handler = None

