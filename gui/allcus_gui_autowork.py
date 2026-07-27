from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta
import re
import time
import threading

from PyQt5.QtCore import QThread, pyqtSignal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

from utils.allcus_logger import ALLCUSLogger
from core.allcus_scraper import (
    ALLCUSScraper,
    DOWNLOAD_SUCCESS,
    DOWNLOAD_UNAVAILABLE,
    DOWNLOAD_FAILED,
    DOWNLOAD_CANCELLED,
)
from core.allcus_duplicate_checker import ALLCUSDuplicateChecker
from core.allcus_converter import ALLCUSConverter
import logging
from core.allcus_excel import ALLCUSExcelGenerator


class AutomationWorker(QThread):
    """Worker thread for running automation"""
    
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str, int, int)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, court: str, start_date: str, end_date: str, year: str, run_folder: Path, headless: bool = True):
        super().__init__()
        self.court = court
        self.start_date = start_date
        self.end_date = end_date
        self.year = year
        self.run_folder = run_folder
        self.headless = headless
        self.driver: Optional[webdriver.Chrome] = None
        self.logger: Optional[ALLCUSLogger] = None
        self._cancelled = False
        self._cancel_requested = False
        self._cancel_interrupt_started = False
        self._cancel_completion_logged = False
        self._finished_emitted = False
        self.last_duplicate_filename: Optional[str] = None
        self.last_duplicate_sid: Optional[str] = None
        self.last_duplicate_date: Optional[str] = None
        self.unavailable_download_count = 0
    
    def cancel(self):
        """Cancel the automation"""
        already_requested = self._cancel_requested
        self._cancelled = True
        self._cancel_requested = True
        # Suppress noisy retry warnings during cancellation
        logging.getLogger("urllib3").setLevel(logging.ERROR)
        logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
        if self.logger and not already_requested:
            self.logger.info("Cancellation requested")
        self._interrupt_webdriver_for_cancel()

    def _interrupt_webdriver_for_cancel(self):
        """Interrupt a blocking Selenium call without blocking the GUI thread."""
        if self._cancel_interrupt_started or not self.driver:
            return

        self._cancel_interrupt_started = True
        driver = self.driver

        def quit_driver():
            shutdown_timer = threading.Timer(
                5.0,
                lambda: self._terminate_driver_service(driver),
            )
            shutdown_timer.daemon = True
            shutdown_timer.start()
            try:
                driver.quit()
            except Exception:
                self._terminate_driver_service(driver)
            finally:
                shutdown_timer.cancel()

        threading.Thread(
            target=quit_driver,
            name="ALLCUSCancelDriverQuit",
            daemon=True,
        ).start()

    def _terminate_driver_service(self, driver):
        """Terminate the ChromeDriver service if graceful quit is stuck."""
        try:
            service = getattr(driver, "service", None)
            process = getattr(service, "process", None)
            if process and process.poll() is None:
                process.terminate()
        except Exception:
            pass

    def _shutdown_driver(self):
        """Close and quit the driver safely in the worker thread."""
        driver = self.driver
        if not driver:
            return
        if self._cancelled and self._cancel_interrupt_started:
            self.driver = None
            return
        try:
            driver.quit()
        except Exception:
            pass
        finally:
            self.driver = None

    def _expand_tracker_date_range(self, start_date: str, end_date: str) -> Tuple[str, str]:
        """
        Expand date range for tracker search: subtract 1 year from start, add 1 year to end.
        
        Args:
            start_date: Start date in MM/dd/yyyy format
            end_date: End date in MM/dd/yyyy format
        
        Returns:
            Tuple of (expanded_start_date, expanded_end_date) in MM/dd/yyyy format
        """
        try:
            # Parse dates
            start_dt = datetime.strptime(start_date, "%m/%d/%Y")
            end_dt = datetime.strptime(end_date, "%m/%d/%Y")
            
            # Expand: subtract 1 year from start, add 1 year to end
            expanded_start = start_dt - timedelta(days=365)
            expanded_end = end_dt + timedelta(days=365)
            
            # Format back to MM/dd/yyyy
            expanded_start_str = expanded_start.strftime("%m/%d/%Y")
            expanded_end_str = expanded_end.strftime("%m/%d/%Y")
            
            return expanded_start_str, expanded_end_str
        except Exception as e:
            # If parsing fails, log and return original dates
            if self.logger:
                self.logger.warning(f"Failed to expand date range, using original: {str(e)}")
            return start_date, end_date

    def _sleep_or_cancel(self, seconds: float):
        """Sleep in short increments so cancellation can be detected promptly."""
        end_time = time.time() + seconds
        while not self._cancelled and time.time() < end_time:
            time.sleep(0.1)

    def _emit_cancelled(self):
        """Emit a cancelled completion once."""
        if self._finished_emitted:
            return
        self._finished_emitted = True
        self.finished_signal.emit(False, "CANCELLED")

    def _log_cancelled_once(self):
        """Write the cancellation completion message once per run."""
        if self._cancel_completion_logged:
            return
        self._cancel_completion_logged = True
        if self.logger:
            self.logger.info("Automation cancelled by user")

    def _last_duplicate_details(self) -> Optional[tuple]:
        if self.last_duplicate_filename or self.last_duplicate_sid or self.last_duplicate_date:
            return (
                self.last_duplicate_filename,
                self.last_duplicate_sid,
                self.last_duplicate_date,
            )
        return None

    def _record_last_duplicate_details(self, checker, duplicates) -> Optional[tuple]:
        """Store the most recent duplicate collection details for the completion prompt."""
        if not duplicates:
            return self._last_duplicate_details()

        duplicate_records = checker.extract_duplicate_documents(duplicates)
        if duplicate_records:
            most_recent = max(
                (rec for rec in duplicate_records if rec[2] is not None),
                key=lambda x: x[2],
                default=None
            )
            if most_recent:
                self.last_duplicate_filename = most_recent[0]
                self.last_duplicate_sid = most_recent[1]
                self.last_duplicate_date = f"{most_recent[2].month}/{most_recent[2].day}/{most_recent[2].year}"

        return self._last_duplicate_details()

    def _log_summary(
        self,
        includes_count: int,
        duplicates_count: int,
        errors_count: int,
        unavailable_count: int = 0,
        last_duplicate_details: Optional[tuple] = None,
    ):
        """Log a summary report for the run"""
        if not self.logger:
            return
        self.logger.info("--------------DONE--------------")
        self.logger.info(f"Includes: {includes_count}")
        self.logger.info(f"Duplicates: {duplicates_count}")
        if unavailable_count:
            self.logger.info(f"Not Available for Download: {unavailable_count}")
        self.logger.info(f"Errors: {errors_count}")
        if last_duplicate_details:
            filename, sid, routed_date = last_duplicate_details
            self.logger.info(f"Last Collected Filename: {filename or 'N/A'}")
            self.logger.info(f"Last Collected SID: {sid or 'N/A'}")
            self.logger.info(f"Last Collected Routed Date: {routed_date or 'N/A'}")
        self.logger.info("--------------DONE--------------")
    
    def run(self):
        """Run the automation process"""
        try:
            # Initialize logger
            self.logger = ALLCUSLogger(self.run_folder, self.log_signal)
            self.logger.info("Starting ALLCUS automation")
            
            # Ensure any previous driver is cleaned up
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            
            # Create Chrome driver with download preferences
            self.logger.info("Initializing Chrome browser")
            chrome_options = ChromeOptions()
            
            # Enable headless mode only if requested
            if self.headless:
                self.logger.info("Running in headless mode (browser hidden)")
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--disable-software-rasterizer")
            else:
                self.logger.info("Running in visible mode (browser visible for debugging)")
            
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            prefs = {
                "download.default_directory": str(self.run_folder.resolve()),
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
                "plugins.always_open_pdf_externally": True,
            }
            chrome_options.add_experimental_option("prefs", prefs)
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(300)
            self.driver.set_script_timeout(30)
            
            # Enable downloads via CDP
            try:
                self.driver.execute_cdp_cmd("Page.setDownloadBehavior", {
                    "behavior": "allow",
                    "downloadPath": str(self.run_folder.resolve()),
                })
            except Exception:
                pass
            
            # Step 1: Web Scraping
            if self._cancelled:
                return
            
            scraper = ALLCUSScraper(
                self.driver,
                self.logger,
                self.court,
                self.start_date,
                self.end_date,
                self.year,
                cancel_check=lambda: self._cancelled,
            )
            
            # Navigate to site
            if self._cancelled:
                return
            try:
                if not scraper.navigate_to_site():
                    if self._cancelled:
                        return  # Don't report error if cancelled
                    self.finished_signal.emit(False, "PAGE_LOAD_FAILED")
                    return
            except Exception as nav_error:
            # Check if this is a connection error due to cancellation
                is_connection_error = any(keyword in str(nav_error).lower() for keyword in [
                    'connection', 'connection refused', 'session', 'invalid session',
                    'disconnected', 'broken pipe', 'target machine actively refused',
                    'remote end closed', 'connection aborted'
                ])
                if self._cancelled and is_connection_error:
                    return  # Don't report error if cancelled
                # Re-raise if not cancelled
                raise
            
            # Apply filters
            if self._cancelled:
                return
            if not scraper.apply_filters():
                if self._cancelled:
                    return  # Don't report error if cancelled
                self.finished_signal.emit(False, "Failed to apply filters.")
                return
            
            # Check if any rulings found (with dates if available)
            ruling_dates_map = scraper.get_all_rulings_with_dates()
            if self._cancelled:
                return
            all_rulings = list(ruling_dates_map.keys())
            if not all_rulings:
                all_rulings = scraper.get_all_rulings()
            if self._cancelled:
                return
            if not all_rulings:
                # This will be handled by the GUI to allow date range adjustment
                self.finished_signal.emit(False, "NO_RULINGS_FOUND")
                return
            
            # Step 2: Duplicate Checking
            if self._cancelled:
                return
            
            self.logger.info("Checking for duplicates...")
            checker = ALLCUSDuplicateChecker(
                self.driver,
                self.logger,
                cancel_check=lambda: self._cancelled,
            )
            
            # Open new tab for tracker
            self.driver.execute_script("window.open('');")
            self.driver.switch_to.window(self.driver.window_handles[1])
            
            if self._cancelled:
                return
            if not checker.navigate_to_tracker():
                if self._cancelled:
                    return  # Don't report error if cancelled
                self.finished_signal.emit(False, "Failed to navigate to LN Doc Tracker.")
                return
            
            if self._cancelled:
                return
            if not checker.setup_query():
                if self._cancelled:
                    return  # Don't report error if cancelled
                self.finished_signal.emit(False, "Failed to setup query in tracker.")
                return
            
            if self._cancelled:
                return
            # Expand date range for tracker: -1 year from start, +1 year from end
            # This ensures we catch duplicates even if users upload old documents
            tracker_start_date, tracker_end_date = self._expand_tracker_date_range(self.start_date, self.end_date)
            if self.logger:
                self.logger.info(f"Tracker search using expanded date range: {tracker_start_date} to {tracker_end_date}")
            if not checker.enter_search_criteria(tracker_start_date, tracker_end_date):
                if self._cancelled:
                    return  # Don't report error if cancelled
                self.finished_signal.emit(False, "Failed to enter search criteria.")
                return
            
            if self._cancelled:
                return
            if not checker.wait_for_report():
                if self._cancelled:
                    return  # Don't report error if cancelled
                self.finished_signal.emit(False, "Report failed to load.")
                return
            
            tracker_dockets = checker.extract_docket_numbers()
            unique_rulings, duplicates = checker.check_duplicates(all_rulings, tracker_dockets)
            last_duplicate_details = self._record_last_duplicate_details(checker, duplicates)
            
            if not unique_rulings:
                duplicates_count = max(0, len(all_rulings))
                self._log_summary(0, duplicates_count, 0, last_duplicate_details=last_duplicate_details)
                self.finished_signal.emit(False, "No unique rulings found after duplicate check.")
                return
            
            # Step 3: Download documents
            if self._cancelled:
                return
            
            unique_label = "ruling" if len(unique_rulings) == 1 else "rulings"
            self.logger.info(f"Downloading {len(unique_rulings)} unique {unique_label}")
            download_total = len(unique_rulings)
            if download_total > 0:
                self.progress_signal.emit(0, "download", 0, download_total)
            
            # Close tracker tab and switch back to court site tab
            if len(self.driver.window_handles) > 1:
                self.driver.close()  # Close tracker tab
                self.driver.switch_to.window(self.driver.window_handles[0])
            else:
                # If only one tab, navigate back to court site
                self.driver.get("https://rulings.cbp.gov/search")
                self._sleep_or_cancel(2)
            
            # Filter out invalid docket numbers and extract valid ones
            valid_docket_numbers = []
            valid_rulings = []
            self.logger.info(f"Processing {len(unique_rulings)} unique {unique_label} to extract docket numbers")
            
            for ruling in unique_rulings:
                self.logger.debug(f"Processing ruling: {repr(ruling)}")
                
                # Extract docket number - should be alphanumeric and match pattern
                parts = ruling.split()
                self.logger.debug(f"Ruling split into parts: {parts}")
                
                if len(parts) >= 2:
                    # For rulings like "HQ H350894", the docket number is the last part "H350894"
                    docket_number = parts[-1]
                    self.logger.debug(f"Extracted docket number (from last part): {docket_number}")
                else:
                    docket_number = ruling
                    self.logger.debug(f"Using full ruling as docket number: {docket_number}")
                
                # Validate docket number - should start with H or N followed by digits
                # Pattern: H followed by digits, or N followed by digits
                if re.match(r'^[HN]\d+$', docket_number):
                    self.logger.info(f"Valid docket number extracted: {docket_number} (from ruling: {ruling})")
                    valid_docket_numbers.append(docket_number)
                    valid_rulings.append(ruling)
                else:
                    self.logger.warning(f"Skipping invalid docket number: {docket_number} (from ruling: {ruling})")
            
            if not valid_docket_numbers:
                duplicates_count = max(0, len(all_rulings) - len(unique_rulings))
                errors_count = max(0, len(unique_rulings))
                self._log_summary(0, duplicates_count, errors_count)
                self.finished_signal.emit(False, "No valid docket numbers found to download.")
                return
            
            valid_label = "ruling" if len(valid_docket_numbers) == 1 else "rulings"
            self.logger.info(f"Downloading {len(valid_docket_numbers)} valid {valid_label}")
            
            download_total = len(valid_docket_numbers)
            downloaded_rulings = []
            unavailable_count = 0
            download_errors_count = 0
            for idx, (docket_number, ruling_text) in enumerate(zip(valid_docket_numbers, valid_rulings), start=1):
                if self._cancelled:
                    break
                
                download_status = scraper.download_ruling(docket_number, str(self.run_folder))
                if download_status == DOWNLOAD_SUCCESS:
                    downloaded_rulings.append(ruling_text)
                elif download_status == DOWNLOAD_UNAVAILABLE:
                    unavailable_count += 1
                elif download_status == DOWNLOAD_CANCELLED:
                    break
                elif download_status == DOWNLOAD_FAILED:
                    download_errors_count += 1
                else:
                    download_errors_count += 1
                self._sleep_or_cancel(2)  # Wait between downloads, but remain responsive to cancel
                if download_total > 0:
                    progress_value = int((idx / download_total) * 50)
                    self.progress_signal.emit(progress_value, "download", idx, download_total)

            if self._cancelled:
                return

            self.unavailable_download_count = unavailable_count
            
            if not downloaded_rulings:
                duplicates_count = max(0, len(all_rulings) - len(unique_rulings))
                self._log_summary(
                    0,
                    duplicates_count,
                    download_errors_count,
                    unavailable_count=unavailable_count,
                    last_duplicate_details=last_duplicate_details,
                )
                if unavailable_count and not download_errors_count:
                    self.finished_signal.emit(False, "NO_DOWNLOADS_AVAILABLE")
                else:
                    self.finished_signal.emit(False, "No files were downloaded.")
                return

            # Wait for downloads to complete
            self.logger.info("Waiting for downloads to finish...")
            self._sleep_or_cancel(10)  # Give time for downloads, but remain responsive to cancel
            
            # Step 4: Convert PDFs to DOCX
            if self._cancelled:
                return
            
            self.logger.info("Converting PDFs to DOCX")
            converter = ALLCUSConverter(self.logger)
            pdf_files = list(self.run_folder.glob("*.pdf"))
            convert_total = len(pdf_files)
            if convert_total > 0:
                self.progress_signal.emit(50, "convert", 0, convert_total)
            
            def conversion_progress(processed, total):
                if total > 0:
                    progress_value = 50 + int((processed / total) * 50)
                    self.progress_signal.emit(progress_value, "convert", processed, total)
            
            docket_dates = {}
            if ruling_dates_map:
                for ruling_text, date_text in ruling_dates_map.items():
                    parts = ruling_text.split()
                    if parts:
                        docket_dates[parts[-1]] = date_text

            converted_files = converter.convert_all_pdfs(
                self.run_folder,
                self.court,
                downloaded_rulings,
                ruling_dates=docket_dates,
                progress_callback=conversion_progress
            )
            
            if not converted_files:
                duplicates_count = max(0, len(all_rulings) - len(unique_rulings))
                errors_count = download_errors_count + max(0, len(downloaded_rulings))
                self._log_summary(
                    0,
                    duplicates_count,
                    errors_count,
                    unavailable_count=unavailable_count,
                    last_duplicate_details=last_duplicate_details,
                )
                self.finished_signal.emit(False, "No files were converted.")
                return
            
            # Step 5: Generate Excel report
            if self._cancelled:
                return
            
            self.logger.info("Generating Excel report")
            excel_gen = ALLCUSExcelGenerator(self.logger)
            excel_gen.generate_report(self.run_folder, self.court, converted_files)
            
            # Summary log (report-style)
            duplicates_count = max(0, len(all_rulings) - len(unique_rulings))
            includes_count = len(converted_files)
            errors_count = download_errors_count + max(0, len(downloaded_rulings) - includes_count)
            self._log_summary(
                includes_count,
                duplicates_count,
                errors_count,
                unavailable_count=unavailable_count,
                last_duplicate_details=last_duplicate_details,
            )
            
            # Close browser
            self.driver.quit()
            self.driver = None
            
            self.logger.info("Automation completed successfully")
            self._finished_emitted = True
            processed_label = "document" if len(converted_files) == 1 else "documents"
            self.finished_signal.emit(True, f"Successfully processed {len(converted_files)} {processed_label}.")
            
        except Exception as e:
            # If cancelled, don't log as error - Selenium can fail in many ways
            # once the browser is intentionally closed to break a blocking call.
            if self._cancelled:
                self._log_cancelled_once()
                # Don't emit error signal for cancelled operations
                return
            
            # Otherwise, log and report the error
            error_msg = f"Error during automation: {str(e)}"
            if self.logger:
                self.logger.error(error_msg)
            self._finished_emitted = True
            self.finished_signal.emit(False, error_msg)
        finally:
            if self._cancelled:
                self._log_cancelled_once()
            self._shutdown_driver()
            if self.logger:
                self.logger.close()
            if self._cancelled:
                self._emit_cancelled()


