"""
Web Scraping Module for ALLCUS RPA
Handles web automation for court site scraping
"""

import time
from typing import List, Optional, Callable
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException


DOWNLOAD_SUCCESS = "downloaded"
DOWNLOAD_UNAVAILABLE = "unavailable"
DOWNLOAD_FAILED = "failed"
DOWNLOAD_CANCELLED = "cancelled"


class ALLCUSScraper:
    """Web scraper for CBP court rulings site"""

    FILTER_BUTTON_XPATH = (
        '//*[@id="main-content"]/app-root/div/div[1]/app-header/div/div[2]/div/'
        'mat-toolbar/mat-toolbar-row[2]/div/app-search/div/div/div/div/button/span[3]'
    )

    SEARCH_BUTTON_XPATH = (
        '//*[@id="main-content"]/app-root/div/div[1]/app-header/div/div[2]/div/'
        'mat-toolbar/mat-toolbar-row[2]/div/app-search/div/div/div[1]/button/span[4]'
    )

    NEXT_PAGE_SPAN_XPATH = (
        '//*[@id="main-content"]/app-root/div/div[2]/div/app-search-results/div/div/div[1]/'
        'mat-paginator/div/div/div[2]/button[2]/span[3]'
    )

    def __init__(
        self,
        driver: webdriver.Chrome,
        logger,
        court: str,
        start_date: str,
        end_date: str,
        year: str,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        """
        Initialize scraper

        Args:
            driver: Selenium Chrome driver
            logger: ALLCUSLogger instance
            court: "ALLCUS_HQ" or "ALLCUS_NY"
            start_date: Start date in format MM/DD/YYYY
            end_date: End date in format MM/DD/YYYY
            year: Current year (YYYY)
        """
        self.driver = driver
        self.logger = logger
        self.court = court
        self.start_date = start_date
        self.end_date = end_date
        self.year = year
        self._cancel_check = cancel_check
        self.base_url = "https://rulings.cbp.gov/search"

        if court == "ALLCUS_HQ":
            self.court_prefix = "HQ H"
            self.court_option_text = "HQ"
        elif court == "ALLCUS_NY":
            self.court_prefix = "NY N"
            self.court_option_text = "NY"
        else:
            raise ValueError(f"Invalid court: {court}")

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

    def _has_download_unavailable_notice(self, docket_number: str) -> bool:
        """Return True when CROSS shows the download-unavailable toast."""
        needle = "not available for download"
        docket_needle = docket_number.lower()
        try:
            text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            return needle in text and docket_needle in text
        except Exception:
            return False

    def _get_first_result_signature(self) -> str:
        """
        Return a stable text signature for the current results page.
        Used to verify that pagination actually changed the page.
        """
        try:
            first_row = self.driver.find_element(By.XPATH, '(//mat-table//mat-row)[1]')
            return first_row.text.strip()
        except Exception:
            try:
                first_row = self.driver.find_element(By.XPATH, '(//table//tr)[2]')
                return first_row.text.strip()
            except Exception:
                return ""

    def _get_next_page_button(self):
        """
        Return the actual clickable next-page button.
        Prefer the semantic selector first, then fall back to the confirmed XPath.
        """
        selectors = [
            (By.XPATH, '//button[@aria-label="Next page"]'),
            (
                By.XPATH,
                '//*[@id="main-content"]/app-root/div/div[2]/div/app-search-results/div/div/div[1]/'
                'mat-paginator/div/div/div[2]/button[2]'
            ),
            (By.XPATH, self.NEXT_PAGE_SPAN_XPATH),
        ]

        for by, selector in selectors:
            try:
                elem = self._wait_until(
                    WebDriverWait(self.driver, 5, poll_frequency=0.2),
                    EC.presence_of_element_located((by, selector))
                )

                # If selector found a child span, climb to the parent button
                if elem.tag_name.lower() != "button":
                    elem = elem.find_element(By.XPATH, "./ancestor::button[1]")

                return elem
            except Exception:
                continue

        return None

    def _go_to_next_results_page(self, current_page_num: int) -> bool:
        """
        Click the paginator next button and verify the results changed.

        Returns:
            True if the page advanced.
            False if there is no next page, the button is disabled,
            not clickable, or the page content did not change.
        """
        next_button = self._get_next_page_button()

        if not next_button:
            self.logger.info("Reached last page")
            return False

        try:
            disabled_attr = next_button.get_attribute("disabled")
            aria_disabled = (next_button.get_attribute("aria-disabled") or "").lower()
            aria_label = next_button.get_attribute("aria-label") or ""
            button_class = next_button.get_attribute("class") or ""

            self.logger.debug(
                f"Next button state: aria-label={aria_label!r}, "
                f"disabled={disabled_attr!r}, aria-disabled={aria_disabled!r}, "
                f"class={button_class!r}, enabled={next_button.is_enabled()}, "
                f"displayed={next_button.is_displayed()}"
            )

            # Reliable disabled checks only
            if disabled_attr is not None:
                self.logger.info("Reached last page")
                return False

            if aria_disabled == "true":
                self.logger.info("Reached last page")
                return False

            if not next_button.is_displayed():
                self.logger.info("Reached last page")
                return False

            if not next_button.is_enabled():
                self.logger.info("Reached last page")
                return False

        except Exception as e:
            self.logger.warning(f"Error checking next page button state: {type(e).__name__}: {e!r}")
            return False

        before_signature = self._get_first_result_signature()
        if not before_signature:
            self.logger.warning("Could not capture current page signature before pagination")
            return False

        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                next_button
            )
            self._sleep(0.5)

            self.driver.execute_script("arguments[0].click();", next_button)

            self._wait_until(
                WebDriverWait(self.driver, 15, poll_frequency=0.2),
                lambda d: self._get_first_result_signature() != before_signature
            )

            self.logger.info(f"Moved to page {current_page_num + 1}")
            self._sleep(1)
            return True

        except Exception as e:
            self.logger.info("Reached last page")
            self.logger.debug(f"Pagination stopped: {type(e).__name__}: {e!r}")
            return False

    def navigate_to_site(self) -> bool:
        """Navigate to ALLCUS site"""
        if self._is_cancelled():
            self.logger.info("Navigation aborted due to cancellation")
            return False
        try:
            self.logger.info(f"Navigating to {self.base_url}")
            self.driver.get(self.base_url)

            wait = WebDriverWait(self.driver, 30, poll_frequency=0.2)

            self._wait_until(wait, EC.presence_of_element_located((By.TAG_NAME, "body")))
            self._wait_until(wait, EC.visibility_of_element_located((By.XPATH, self.FILTER_BUTTON_XPATH)))
            self._wait_until(wait, EC.element_to_be_clickable((By.XPATH, self.FILTER_BUTTON_XPATH)))

            self._sleep(1.5)

            self.logger.info("Page loaded successfully")
            return True

        except Exception as e:
            if self._is_cancelled():
                self.logger.info("Navigation interrupted due to cancellation")
                return False
            self.logger.error(f"Error navigating to site: {type(e).__name__}: {e!r}")
            return False

    def apply_filters(self) -> bool:
        """Apply all filters to search page"""
        if self._is_cancelled():
            self.logger.info("Filter application aborted due to cancellation")
            return False
        try:
            wait = WebDriverWait(self.driver, 30, poll_frequency=0.2)

            # 1. Wait for filter control to fully render, then click Filter Icon
            self.logger.info("Waiting for filter icon to become ready")
            filter_icon = self._wait_until(
                wait,
                EC.visibility_of_element_located((By.XPATH, self.FILTER_BUTTON_XPATH))
            )
            filter_icon = self._wait_until(
                wait,
                EC.element_to_be_clickable((By.XPATH, self.FILTER_BUTTON_XPATH))
            )

            self._sleep(1.5)

            self.logger.info("Clicking filter icon with JavaScript")
            self.driver.execute_script("arguments[0].click();", filter_icon)

            self._sleep(1)

            # 2. Enter current year
            self.logger.info(f"Entering year: {self.year}")
            year_input = self._wait_until(
                wait,
                EC.visibility_of_element_located((By.XPATH, '//*[@id="mat-input-0"]'))
            )
            year_input.clear()
            year_input.send_keys(self.year)
            self._sleep(0.5)

            # 3. Open Court Selection dropdown
            self.logger.info("Clicking Court Selection dropdown with JavaScript")
            court_select = self._wait_until(
                wait,
                EC.element_to_be_clickable((By.XPATH, '//*[@id="mat-select-value-0"]'))
            )
            self.driver.execute_script("arguments[0].click();", court_select)

            self._sleep(1)

            # 4. Select court option by visible text
            self.logger.info(f"Selecting court option: {self.court}")

            court_option_xpath_exact = (
                f'//mat-option//span[normalize-space()="{self.court_option_text}"]'
            )
            court_option_xpath_contains = (
                f'//mat-option//span[contains(normalize-space(), "{self.court_option_text}")]'
            )

            try:
                court_option = self._wait_until(
                    wait,
                    EC.visibility_of_element_located((By.XPATH, court_option_xpath_exact))
                )
            except Exception:
                court_option = self._wait_until(
                    wait,
                    EC.visibility_of_element_located((By.XPATH, court_option_xpath_contains))
                )

            self.driver.execute_script("arguments[0].click();", court_option)

            self._sleep(2)
            self.logger.info(f"Successfully selected court option: {self.court}")

            # 5. Enter start date manually
            self.logger.info(f"Entering start date: {self.start_date}")
            date_from = self._wait_until(
                wait,
                EC.visibility_of_element_located((By.ID, 'mat-input-1'))
            )
            date_from.clear()
            date_from.send_keys(self.start_date)
            self._sleep(0.5)

            # 6. Enter end date manually
            self.logger.info(f"Entering end date: {self.end_date}")
            date_to = self._wait_until(
                wait,
                EC.visibility_of_element_located((By.ID, 'mat-input-2'))
            )
            date_to.clear()
            date_to.send_keys(self.end_date)
            self._sleep(0.5)

            # 7. Click Relevance dropdown
            self.logger.info("Selecting relevance: Newest First")
            relevance_dropdown = self._wait_until(
                wait,
                EC.element_to_be_clickable((By.XPATH, '//*[@id="mat-select-value-2"]'))
            )
            self.driver.execute_script("arguments[0].click();", relevance_dropdown)

            self._sleep(1.5)

            # 8. Select "Ruling Date - Newest First"
            self.logger.info("Selecting 'Ruling Date - Newest First' option")

            newest_option = self._wait_until(
                wait,
                EC.visibility_of_element_located((
                    By.XPATH,
                    '//mat-option//span[normalize-space()="Ruling Date - Newest First"]'
                ))
            )

            self.driver.execute_script("arguments[0].click();", newest_option)

            self._sleep(1)

            # 9. Click Items Per Page dropdown
            self.logger.info("Selecting items per page: 100")
            items_dropdown = self._wait_until(
                wait,
                EC.element_to_be_clickable((By.XPATH, '//*[@id="mat-select-value-3"]'))
            )
            self.driver.execute_script("arguments[0].click();", items_dropdown)

            self._sleep(1.5)

            # 10. Select 100 items per page by visible text
            self.logger.info("Selecting '100' option")
            items_100 = self._wait_until(
                wait,
                EC.visibility_of_element_located((
                    By.XPATH,
                    '//mat-option//span[normalize-space()="100"]'
                ))
            )

            self.driver.execute_script("arguments[0].click();", items_100)

            self._sleep(1)

            # 11. Click Search button
            self.logger.info("Clicking court search button with JavaScript")
            search_button = self._wait_until(
                wait,
                EC.element_to_be_clickable((By.XPATH, self.SEARCH_BUTTON_XPATH))
            )

            self.driver.execute_script("arguments[0].click();", search_button)

            self._sleep(2)

            results_loaded = False
            results_selectors = [
                (By.TAG_NAME, "mat-table"),
                (By.XPATH, '//mat-table//mat-row'),
                (By.XPATH, '//table//tr'),
            ]

            for by, selector in results_selectors:
                try:
                    self._wait_until(
                        WebDriverWait(self.driver, 15, poll_frequency=0.2),
                        EC.presence_of_element_located((by, selector))
                    )
                    results_loaded = True
                    break
                except Exception:
                    continue

            if not results_loaded:
                raise TimeoutError("Search click completed, but no results table appeared.")

            self.logger.info("Filters applied successfully")
            return True

        except Exception as e:
            if self._is_cancelled():
                self.logger.info("Filter application aborted due to cancellation")
                return False
            self.logger.error(f"Error applying filters: {type(e).__name__}: {e!r}")
            return False

    def extract_rulings_from_page(self, page_num: Optional[int] = None) -> List[str]:
        """
        Extract ruling numbers from current page

        Returns:
            List of ruling numbers (e.g., ["HQ H350894", "NY N357085"])
        """
        rulings = []
        try:
            self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.presence_of_element_located((By.TAG_NAME, "mat-table"))
            )

            rows = self.driver.find_elements(By.XPATH, '//mat-table//mat-row')

            if not rows:
                rows = self.driver.find_elements(By.XPATH, '//table//tr')

            page_label = f"page {page_num}" if page_num is not None else "current page"
            self.logger.info(f"Found {len(rows)} rows on {page_label}")

            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "mat-cell")
                    if not cells:
                        cells = row.find_elements(By.TAG_NAME, "td")

                    if len(cells) >= 3:
                        raw_text = cells[2].text.strip()
                        self.logger.debug(f"Raw cell text extracted: {repr(raw_text)}")

                        lines = raw_text.split('\n')
                        ruling_text = None
                        for line in lines:
                            line = line.strip()
                            if line and line.startswith(self.court_prefix):
                                parts = line.split()
                                if len(parts) >= 2:
                                    ruling_text = f"{parts[0]} {parts[1]}"
                                else:
                                    ruling_text = line
                                break

                        if ruling_text:
                            self.logger.debug(
                                f"Extracted ruling: {ruling_text} (from raw: {repr(raw_text)})"
                            )
                            rulings.append(ruling_text)
                        else:
                            self.logger.warning(
                                f"Could not extract ruling from cell text: {repr(raw_text)}"
                            )
                except Exception as e:
                    self.logger.debug(f"Error processing row: {str(e)}")
                    continue

            self.logger.info(f"Extracted {len(rulings)} rulings from {page_label}")
            return rulings

        except Exception as e:
            self.logger.error(f"Error extracting rulings from page: {type(e).__name__}: {e!r}")
            return []

    def extract_rulings_with_dates_from_page(self, page_num: Optional[int] = None) -> List[tuple]:
        """
        Extract ruling numbers and dates from current page.

        Returns:
            List of tuples (ruling_text, date_text)
        """
        results = []
        try:
            self._wait_until(
                WebDriverWait(self.driver, 10, poll_frequency=0.2),
                EC.presence_of_element_located((By.TAG_NAME, "mat-table"))
            )
            rows = self.driver.find_elements(By.XPATH, '//mat-table//mat-row')
            if not rows:
                rows = self.driver.find_elements(By.XPATH, '//table//tr')

            page_label = f"page {page_num}" if page_num is not None else "current page"
            self.logger.info(f"Found {len(rows)} rows with dates on {page_label}")

            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "mat-cell")
                    if not cells:
                        cells = row.find_elements(By.TAG_NAME, "td")

                    if len(cells) < 3:
                        continue

                    raw_text = cells[2].text.strip()
                    lines = raw_text.split('\n')
                    ruling_text = None
                    for line in lines:
                        line = line.strip()
                        if line and line.startswith(self.court_prefix):
                            parts = line.split()
                            if len(parts) >= 2:
                                ruling_text = f"{parts[0]} {parts[1]}"
                            else:
                                ruling_text = line
                            break

                    if not ruling_text:
                        continue

                    date_text = ""
                    for cell in cells:
                        try:
                            class_attr = cell.get_attribute("class") or ""
                            if "mat-column-date" in class_attr:
                                date_text = cell.text.strip()
                                break
                        except Exception:
                            continue

                    results.append((ruling_text, date_text))
                except Exception as e:
                    self.logger.debug(f"Error processing row with date: {str(e)}")
                    continue

            return results
        except Exception as e:
            self.logger.error(f"Error extracting rulings with dates: {type(e).__name__}: {e!r}")
            return []

    def get_all_rulings(self) -> List[str]:
        """
        Navigate through all pages and collect all rulings

        Returns:
            List of all unique ruling numbers
        """
        all_rulings = []
        page_num = 1

        try:
            while True:
                if self._is_cancelled():
                    self.logger.info("Ruling collection aborted due to cancellation")
                    break
                self.logger.info(f"Extracting rulings from page {page_num}")
                page_rulings = self.extract_rulings_from_page(page_num)
                all_rulings.extend(page_rulings)

                if not self._go_to_next_results_page(page_num):
                    break

                page_num += 1

            unique_rulings = []
            seen = set()
            for ruling in all_rulings:
                if ruling not in seen:
                    unique_rulings.append(ruling)
                    seen.add(ruling)

            self.logger.info(f"Total unique rulings found: {len(unique_rulings)}")
            return unique_rulings

        except Exception as e:
            self.logger.error(f"Error getting all rulings: {type(e).__name__}: {e!r}")
            return all_rulings

    def get_all_rulings_with_dates(self) -> dict:
        """
        Navigate through all pages and collect all rulings with dates.

        Returns:
            Mapping of ruling_text -> date_text
        """
        all_rows = []
        page_num = 1

        try:
            while True:
                if self._is_cancelled():
                    self.logger.info("Ruling collection with dates aborted due to cancellation")
                    break
                self.logger.info(f"Extracting rulings from page {page_num}")
                page_rows = self.extract_rulings_with_dates_from_page(page_num)
                all_rows.extend(page_rows)

                if not self._go_to_next_results_page(page_num):
                    break

                page_num += 1

            ruling_dates = {}
            for ruling_text, date_text in all_rows:
                if ruling_text and ruling_text not in ruling_dates:
                    ruling_dates[ruling_text] = date_text

            self.logger.info(f"Total unique rulings found: {len(ruling_dates)}")
            return ruling_dates

        except Exception as e:
            self.logger.error(f"Error getting all rulings with dates: {type(e).__name__}: {e!r}")
            return {}

    def download_ruling(self, docket_number: str, download_folder: str) -> str:
        """
        Download a single ruling document

        Args:
            docket_number: Docket number (e.g., "H350894" or "N357085")
            download_folder: Path to folder where file should be saved

        Returns:
            Download status string: downloaded, unavailable, failed, or cancelled.
        """
        try:
            if self._is_cancelled():
                self.logger.info(f"Download aborted before opening page for {docket_number}")
                return DOWNLOAD_CANCELLED
            from pathlib import Path

            url = f"https://rulings.cbp.gov/ruling/{docket_number}"
            self.logger.info(f"Opening ruling page for {docket_number}")
            self.driver.get(url)

            wait = WebDriverWait(self.driver, 30, poll_frequency=0.2)

            download_path = Path(download_folder)
            before_files = {p.name for p in download_path.iterdir()} if download_path.exists() else set()

            DOWNLOAD_BUTTON_XPATH = (
                '//*[@id="main-content"]/app-root/div/div[2]/div/app-ruling/div/div/'
                'mat-card/app-ruling-detail/div/div/div[1]/div/div[1]/div[2]/div[2]/div/a/span[4]'
            )

            # Wait for page to fully load
            self._wait_until(
                wait,
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            self._wait_until(
                wait,
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            self._sleep(2)

            download_button = self._wait_until(
                wait,
                EC.visibility_of_element_located((By.XPATH, DOWNLOAD_BUTTON_XPATH))
            )
            download_button = self._wait_until(
                wait,
                EC.element_to_be_clickable((By.XPATH, DOWNLOAD_BUTTON_XPATH))
            )

            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                download_button
            )
            self._sleep(0.5)

            self.logger.info(f"Downloading Ruling {docket_number}")
            self.driver.execute_script("arguments[0].click();", download_button)

            # Wait for a new completed file to appear
            timeout_seconds = 30
            poll_interval = 1
            deadline = time.time() + timeout_seconds

            while time.time() < deadline:
                if self._is_cancelled():
                    self.logger.info(f"Download aborted for {docket_number} due to cancellation")
                    return DOWNLOAD_CANCELLED
                if self._has_download_unavailable_notice(docket_number):
                    self.logger.info(f"Not Available for Download: {docket_number}")
                    return DOWNLOAD_UNAVAILABLE
                current_files = {p.name for p in download_path.iterdir()} if download_path.exists() else set()
                new_files = current_files - before_files

                # Ignore temporary/incomplete Chrome files
                completed_files = [
                    name for name in new_files
                    if not name.endswith(".crdownload")
                    and not name.endswith(".tmp")
                    and not name.endswith(".part")
                ]

                if completed_files:
                    confirmed_file = completed_files[0]
                    self.logger.info(f"Download successful for {docket_number}: {confirmed_file}")
                    return DOWNLOAD_SUCCESS

                self._sleep(poll_interval)

            self.logger.error(f"Download failed for {docket_number}: no completed file appeared within {timeout_seconds} seconds")
            return DOWNLOAD_FAILED

        except Exception as e:
            if self._is_cancelled():
                self.logger.info(f"Download interrupted for {docket_number} due to cancellation")
                return DOWNLOAD_CANCELLED
            self.logger.error(f"Error downloading ruling {docket_number}: {type(e).__name__}: {e!r}")
            return DOWNLOAD_FAILED
