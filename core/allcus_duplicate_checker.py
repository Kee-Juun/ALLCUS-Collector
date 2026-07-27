"""
Duplicate Checking Module for ALLCUS RPA
Checks rulings against LN Doc Tracker to find duplicates
"""

import time
import re
from datetime import datetime
from typing import Callable, List, Tuple, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.common.exceptions import WebDriverException


class ALLCUSDuplicateChecker:
    """Duplicate checker using LN Doc Tracker"""
    
    def __init__(self, driver: webdriver.Chrome, logger, cancel_check: Optional[Callable[[], bool]] = None):
        """
        Initialize duplicate checker
        
        Args:
            driver: Selenium Chrome driver
            logger: ALLCUSLogger instance
            cancel_check: Optional callable that returns True when cancellation is requested
        """
        self.driver = driver
        self.logger = logger
        self._cancel_check = cancel_check
        self._tracker_rows_snapshot: Optional[List[List[str]]] = None

    def _is_cancelled(self) -> bool:
        return bool(self._cancel_check and self._cancel_check())

    def _sleep(self, seconds: float):
        """Sleep in short increments so cancellation can be detected promptly."""
        end_time = time.time() + seconds
        while not self._is_cancelled() and time.time() < end_time:
            time.sleep(0.1)

    def _wrap_condition(self, condition):
        def wrapped(driver):
            if self._is_cancelled():
                raise TimeoutException("Cancelled")
            return condition(driver)
        return wrapped

    def _wait_until(self, wait: WebDriverWait, condition):
        return wait.until(self._wrap_condition(condition))
    
    def _is_connection_error(self, exception) -> bool:
        """Check if exception is a connection error (likely due to cancellation)"""
        error_str = str(exception).lower()
        connection_keywords = [
            'connection', 'connection refused', 'session', 'invalid session',
            'disconnected', 'broken pipe', 'target machine actively refused',
            'remote end closed', 'connection aborted', 'connection pool'
        ]
        return any(keyword in error_str for keyword in connection_keywords)
    
    def navigate_to_tracker(self) -> bool:
        """Navigate to LN Doc Tracker site"""
        if self._is_cancelled():
            self.logger.info("Tracker navigation aborted due to cancellation")
            return False
        try:
            self.logger.info("Navigating to LN Doc Tracker")
            self._tracker_rows_snapshot = None
            self.driver.get("https://tcfabprod.lexisnexis.com/ws/TrackerReport/")
            self._sleep(2)
            return True
        except Exception as e:
            # Check if this is a connection error (likely due to cancellation)
            if self._is_connection_error(e):
                self.logger.info("Navigation to tracker interrupted (likely due to cancellation)")
                return False
            self.logger.error(f"Error navigating to tracker: {str(e)}")
            return False
    
    def setup_query(self) -> bool:
        """Navigate through query setup steps"""
        if self._is_cancelled():
            self.logger.info("Tracker query setup aborted due to cancellation")
            return False
        try:
            # 17. Click first Intelligent Query button
            self.logger.info("Clicking first Intelligent Query button")
            first_button = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '/html/body/table/tbody/tr/td[2]/table[3]/tbody/tr[1]/td/a/img'))
            )
            first_button.click()
            self._sleep(2)
            
            # 18. Wait for and click second Intelligent Query button
            self.logger.info("Clicking second Intelligent Query button")
            second_button = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '/html/body/table/tbody/tr/td[2]/center/a/img'))
            )
            second_button.click()
            self._sleep(2)
            
            # 19. Click "Open an Existing Query" radio button
            self.logger.info("Selecting 'Open an Existing Query'")
            radio_button = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '//*[@id="startQuery"]/table/tbody/tr/td[2]/table[2]/tbody/tr[3]/td/input'))
            )
            radio_button.click()
            self._sleep(1)
            
            # 20. Click first Next button
            self.logger.info("Clicking first Next button")
            next_button1 = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '//*[@id="startQuery"]/table/tbody/tr/td[2]/table[2]/tbody/tr[4]/td/input'))
            )
            next_button1.click()
            self._sleep(2)
            
            # 21. Select "PSS Inventory Production Volume (Agency)" option
            self.logger.info("Selecting PSS Inventory Production Volume (Agency)")
            option = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '//*[@id="select1"]/option[19]'))
            )
            option.click()
            self._sleep(1)
            
            # 22. Click second Next button
            self.logger.info("Clicking second Next button")
            next_button2 = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[3]/td/input'))
            )
            next_button2.click()
            self._sleep(2)
            
            # 23. Click third Next button
            self.logger.info("Clicking third Next button")
            next_button3 = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '//input[@type="submit" and @value="  Next  "]'))
            )
            next_button3.click()
            self._sleep(2)
            
            # 24. Click Search button
            self.logger.info("Clicking tracker search button")
            search_button = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[9]/td/input[3]'))
            )
            search_button.click()
            self._sleep(2)
            
            return True
            
        except Exception as e:
            # Check if this is a connection error (likely due to cancellation)
            if self._is_connection_error(e):
                self.logger.info("Query setup interrupted (likely due to cancellation)")
                return False
            self.logger.error(f"Error setting up query: {str(e)}")
            return False
    
    def enter_search_criteria(self, start_date: str, end_date: str) -> bool:
        """
        Enter search criteria (court and date range)
        
        Args:
            start_date: Start date in MM/DD/YYYY format
            end_date: End date in MM/DD/YYYY format
        """
        if self._is_cancelled():
            self.logger.info("Tracker search criteria entry aborted due to cancellation")
            return False
        try:
            # 25. Enter court (always "FDALLCUS")
            self.logger.info("Entering court: FDALLCUS")
            court_input = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.presence_of_element_located((By.XPATH, '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[27]/td[4]/input'))
            )
            court_input.clear()
            court_input.send_keys("FDALLCUS")
            self._sleep(0.5)
            
            # 26. Enter date range (MM/DD/YYYY-MM/DD/YYYY)
            date_range = f"{start_date}-{end_date}"
            self.logger.info(f"Entering date range: {date_range}")
            date_input = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.presence_of_element_located((By.XPATH, '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[33]/td[4]/input'))
            )
            date_input.clear()
            date_input.send_keys(date_range)
            self._sleep(0.5)
            
            # 27. Click Finish button
            self.logger.info("Clicking Finish button")
            finish_button = self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.element_to_be_clickable((By.XPATH, '/html/body/form/table/tbody/tr/td[2]/table[2]/tbody/tr[72]/td/input[5]'))
            )
            finish_button.click()
            self._tracker_rows_snapshot = None
            self._sleep(3)
            
            return True
            
        except Exception as e:
            # Check if this is a connection error (likely due to cancellation)
            if self._is_connection_error(e):
                self.logger.info("Entering search criteria interrupted (likely due to cancellation)")
                return False
            self.logger.error(f"Error entering search criteria: {str(e)}")
            return False
    
    def wait_for_report(self, timeout: int = 60) -> bool:
        """
        Wait for report to load
        
        Args:
            timeout: Maximum wait time in seconds
        """
        if self._is_cancelled():
            self.logger.info("Report wait aborted due to cancellation")
            return False
        try:
            self.logger.info("Waiting for report to load")
            self._wait_until(
                WebDriverWait(self.driver, timeout, poll_frequency=0.2),
                EC.presence_of_element_located((By.XPATH, '/html/body/form/table[2]/tbody/tr[1]/td[8]'))
            )
            self.logger.info("Report loaded successfully")
            return True
        except TimeoutException:
            if self._is_cancelled():
                self.logger.info("Report wait aborted due to cancellation")
                return False
            self.logger.error(f"Report failed to load within {timeout} seconds")
            return False

    def _extract_tracker_rows_snapshot(self, force_refresh: bool = False) -> List[List[str]]:
        """
        Snapshot the tracker report table into plain cell-text lists.

        The snapshot is cached so multiple duplicate-check steps can reuse the
        same report data without walking the live table repeatedly through
        Selenium.
        """
        if self._tracker_rows_snapshot is not None and not force_refresh:
            return self._tracker_rows_snapshot

        try:
            self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.presence_of_element_located((By.XPATH, '/html/body/form/table[2]/tbody/tr[1]/td[8]'))
            )

            row_snapshots = self.driver.execute_script(
                """
                function rowsFromXPath(path) {
                    const result = document.evaluate(
                        path,
                        document,
                        null,
                        XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                        null
                    );
                    const rows = [];
                    for (let i = 0; i < result.snapshotLength; i += 1) {
                        rows.push(result.snapshotItem(i));
                    }
                    return rows;
                }

                let rows = rowsFromXPath('/html/body/form/table[2]/tbody/tr');
                if (!rows.length) {
                    rows = rowsFromXPath('//table[2]//tr');
                }

                return rows.map((row) =>
                    Array.from(row.querySelectorAll('td')).map(
                        (cell) => (cell.textContent || '').trim()
                    )
                );
                """
            )

            if isinstance(row_snapshots, list):
                self._tracker_rows_snapshot = row_snapshots
                return row_snapshots
        except Exception as e:
            self.logger.warning(
                f"JavaScript tracker table extraction failed; falling back to Selenium reads: {str(e)}"
            )

        rows = self.driver.find_elements(By.XPATH, '/html/body/form/table[2]/tbody/tr')
        if not rows:
            rows = self.driver.find_elements(By.XPATH, '//table[2]//tr')

        row_snapshots: List[List[str]] = []
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                row_snapshots.append([cell.text.strip() for cell in cells])
            except Exception:
                row_snapshots.append([])

        self._tracker_rows_snapshot = row_snapshots
        return row_snapshots
    
    def extract_docket_numbers(self) -> List[str]:
        """
        Extract docket numbers from the report
        
        Returns:
            List of docket numbers found in the report
        """
        docket_numbers = []
        try:
            row_snapshots = self._extract_tracker_rows_snapshot()

            # Skip header row (first row)
            for cells in row_snapshots[1:]:
                try:
                    if len(cells) >= 3:
                        filename_text = (cells[2] or "").strip()  # Index 2 for 3rd column (0-indexed)
                        if filename_text:
                            self.logger.debug(f"Extracted raw filename from tracker: {repr(filename_text)}")
                            # Extract docket number from filename (e.g., H350894 or N357085)
                            # Use a permissive pattern since filenames include underscores/dots
                            match = re.search(r'([HN]\d{5,})', filename_text.upper())
                            if match:
                                docket_text = match.group(1)
                                self.logger.debug(f"Extracted docket from filename: {docket_text}")
                                docket_numbers.append(docket_text)
                            else:
                                self.logger.warning(f"No docket pattern found in filename: {repr(filename_text)}")
                        else:
                            self.logger.debug("Empty filename text found in tracker row, falling back to docket column")
                            if len(cells) >= 8:
                                fallback_docket = (cells[7] or "").strip()
                                if fallback_docket:
                                    self.logger.debug(f"Extracted fallback docket from column 8: {repr(fallback_docket)}")
                                    docket_numbers.append(fallback_docket)
                                else:
                                    self.logger.debug("Empty fallback docket text found in tracker row")
                    else:
                        self.logger.debug(f"Row has only {len(cells)} cells, expected at least 3")
                except Exception as e:
                    self.logger.debug(f"Error processing row: {str(e)}")
                    continue
            
            self.logger.info(f"Extracted {len(docket_numbers)} docket numbers from report")
            # Log first few examples for debugging
            if docket_numbers:
                sample_size = min(10, len(docket_numbers))
                self.logger.debug(f"Sample of extracted docket numbers (first {sample_size}): {docket_numbers[:sample_size]}")
                
                # Check for HQ dockets (starting with H or HQ)
                hq_dockets = [d for d in docket_numbers if d.strip().upper().startswith('H') or 'HQ' in d.strip().upper()]
                if hq_dockets:
                    self.logger.debug(f"Found {len(hq_dockets)} HQ dockets in tracker report")
                    sample_hq = hq_dockets[:20] if len(hq_dockets) > 20 else hq_dockets
                    self.logger.debug(f"Sample HQ dockets from tracker: {sample_hq}")
                else:
                    self.logger.debug("No HQ dockets found in tracker report - only NY dockets detected")
                    
            return docket_numbers
            
        except Exception as e:
            self.logger.error(f"Error extracting docket numbers: {str(e)}")
            return []

    def extract_duplicate_documents(self, duplicates: List[str]) -> List[Tuple[str, Optional[str], Optional[datetime]]]:
        """
        Extract duplicate filenames and routing dates from the report.

        Args:
            duplicates: List of duplicate rulings (e.g., ["HQ H350894", "NY N357085"])

        Returns:
            List of tuples: (filename, sid or None, datetime or None)
        """
        if not duplicates:
            return []

        duplicate_dockets = set()
        for ruling in duplicates:
            parts = ruling.strip().upper().split()
            if len(parts) >= 2:
                duplicate_dockets.add(parts[-1])
            else:
                duplicate_dockets.add(ruling.strip().upper())

        records: List[Tuple[str, Optional[str], Optional[datetime]]] = []
        try:
            row_snapshots = self._extract_tracker_rows_snapshot()

            for cells in row_snapshots[1:]:
                if len(cells) < 3:
                    continue

                filename_text = (cells[2] or "").strip() if len(cells) >= 3 else ""
                sid_text = None
                if filename_text:
                    lower_name = filename_text.lower()
                    if ".docx." in lower_name:
                        base_idx = lower_name.find(".docx.")
                        sid_text = filename_text[base_idx + len(".docx."):]
                        filename_text = filename_text[:base_idx + len(".docx")]
                    elif ".pdf." in lower_name:
                        base_idx = lower_name.find(".pdf.")
                        sid_text = filename_text[base_idx + len(".pdf."):]
                        filename_text = filename_text[:base_idx + len(".pdf")]
                if sid_text:
                    sid_text = sid_text.strip()
                    if "." in sid_text:
                        sid_text = sid_text.split(".", 1)[0].strip()
                docket_from_row = ""
                if filename_text:
                    match = re.search(r'([HN]\d{5,})', filename_text.upper())
                    if match:
                        docket_from_row = match.group(1)
                if not docket_from_row and len(cells) >= 8:
                    docket_from_row = (cells[7] or "").strip().upper()

                if not docket_from_row or docket_from_row not in duplicate_dockets:
                    continue

                routing_date = None
                if len(cells) >= 11:
                    raw_date = (cells[10] or "").strip()
                    if raw_date:
                        date_part = raw_date.split()[0]
                        try:
                            routing_date = datetime.strptime(date_part, "%Y-%m-%d")
                        except Exception:
                            routing_date = None

                records.append((filename_text or "Unknown filename", sid_text, routing_date))

            return records
        except Exception as e:
            self.logger.error(f"Error extracting duplicate document dates: {str(e)}")
            return []
    
    def check_duplicates(self, court_rulings: List[str], tracker_dockets: List[str]) -> Tuple[List[str], List[str]]:
        """
        Compare court rulings against tracker dockets and remove duplicates
        
        Args:
            court_rulings: List of ruling numbers from court site (e.g., ["HQ H350894", "NY N357085"])
            tracker_dockets: List of docket numbers from tracker (e.g., ["H350894", "N357085"])
        
        Returns:
            List of unique ruling numbers (duplicates removed)
        """
        unique_rulings = []
        duplicates = []
        
        self.logger.info(f"Comparing {len(court_rulings)} court rulings against {len(tracker_dockets)} tracker dockets")
        
        # First, let's check if the court docket numbers exist in the tracker in ANY format
        court_docket_nums = []
        for ruling in court_rulings:
            parts = ruling.strip().upper().split()
            if len(parts) >= 2:
                court_docket_nums.append(parts[-1])
        
        self.logger.debug(f"Court docket numbers we're looking for: {court_docket_nums}")
        # Search for them in raw tracker data
        for docket_num in court_docket_nums:
            found_formats = []
            for tracker_docket in tracker_dockets:
                if docket_num in tracker_docket.upper():
                    found_formats.append(tracker_docket)
            if found_formats:
                self.logger.debug(f"Found docket {docket_num} in tracker in these formats: {found_formats}")
            else:
                self.logger.debug(f"Docket {docket_num} NOT found in raw tracker data at all!")
        
        # Convert tracker dockets to a set for fast lookup
        # Tracker dockets might be in various formats, so we'll extract the core docket number
        tracker_set = set()
        self.logger.debug("Processing tracker dockets to extract core docket numbers...")
        
        # Log first few raw tracker dockets for debugging
        sample_raw = tracker_dockets[:10] if len(tracker_dockets) > 10 else tracker_dockets
        self.logger.debug(f"Sample of raw tracker docket numbers (first {len(sample_raw)}): {sample_raw}")
        
        for docket in tracker_dockets:
            # Extract alphanumeric part (e.g., "H350894" from "HQ H350894" or just "H350894")
            original = docket
            docket_clean = docket.strip().upper()
            # Remove any prefixes like "HQ " or "NY "
            if " " in docket_clean:
                parts = docket_clean.split()
                if len(parts) > 1:
                    docket_clean = parts[-1]  # Take last part
            tracker_set.add(docket_clean)
        
        # Log sample of cleaned tracker set for debugging
        sample_tracker = sorted(list(tracker_set))[:20]
        self.logger.debug(f"Sample of cleaned tracker docket numbers (first 20, sorted): {sample_tracker}")
        self.logger.info(f"Total unique cleaned docket numbers in tracker set: {len(tracker_set)}")
        
        # Check each court ruling
        self.logger.info("Checking court rulings against tracker...")
        for ruling in court_rulings:
            # Extract docket number from ruling (e.g., "H350894" from "HQ H350894")
            ruling_original = ruling
            ruling_clean = ruling.strip().upper()
            if " " in ruling_clean:
                parts = ruling_clean.split()
                if len(parts) >= 2:
                    docket_num = parts[-1]  # Last part is the docket number
                else:
                    docket_num = ruling_clean
            else:
                docket_num = ruling_clean
            
            self.logger.debug(f"Checking court ruling: {ruling_original} -> extracted docket: '{docket_num}'")
            
            # Check if it's a duplicate
            if docket_num in tracker_set:
                duplicates.append(ruling)
                self.logger.debug(f"DUPLICATE FOUND: {ruling} (docket: {docket_num}) - EXISTS in tracker")
            else:
                unique_rulings.append(ruling)
                self.logger.debug(f"UNIQUE: {ruling} (docket: {docket_num}) - NOT found in tracker (will download)")
        
        self.logger.info(f"Duplicate check complete: Found {len(duplicates)} duplicates, {len(unique_rulings)} unique rulings")
        if duplicates:
            self.logger.debug(f"Duplicate rulings: {duplicates}")
        if unique_rulings:
            self.logger.debug(f"Unique rulings (will download): {unique_rulings}")
        
        return unique_rulings, duplicates

