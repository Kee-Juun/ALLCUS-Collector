"""
PDF to DOCX Conversion Module for ALLCUS RPA
Converts downloaded PDF files to DOCX format
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional
from pdf2docx import Converter


class ALLCUSConverter:
    """PDF to DOCX converter for ALLCUS documents"""
    
    def __init__(self, logger):
        """
        Initialize converter
        
        Args:
            logger: ALLCUSLogger instance
        """
        self.logger = logger
    
    def extract_docket_number(self, ruling: str) -> str:
        """
        Extract docket number from ruling string
        
        Args:
            ruling: Ruling string (e.g., "HQ H350894" or "NY N357085")
        
        Returns:
            Docket number (e.g., "H350894" or "N357085")
        """
        parts = ruling.split()
        if len(parts) >= 2:
            return parts[-1]  # Last part is the docket number
        return ruling
    
    def generate_filename(self, docket_number: str, court: str, date_str: str = "") -> str:
        """
        Generate filename using template: LDC_SMD_docketnumber_MMDDYYYY_E2E
        
        Args:
            docket_number: Docket number (e.g., "H350894")
            court: Court prefix ("HQ" or "NY")
        
        Returns:
            Generated filename (e.g., "LDC_SMD_H345634_12162025_E2E.docx")
        """
        if date_str:
            try:
                parsed = datetime.strptime(date_str.strip(), "%m/%d/%Y")
                date_str = parsed.strftime("%m%d%Y")
            except Exception:
                date_str = date_str.replace("/", "")
        else:
            now = datetime.now()
            date_str = now.strftime("%m%d%Y")
        filename = f"LDC_SMD_{docket_number}_{date_str}_E2E.docx"
        return filename
    
    def convert_pdf_to_docx(self, pdf_path: Path, docx_path: Path) -> bool:
        """
        Convert a single PDF file to DOCX
        
        Args:
            pdf_path: Path to PDF file
            docx_path: Path where DOCX should be saved
        
        Returns:
            True if conversion successful, False otherwise
        """
        try:
            self.logger.info(f"Converting {pdf_path.name} to DOCX")
            cv = Converter(str(pdf_path))
            cv.convert(str(docx_path))
            cv.close()
            self.logger.info(f"Successfully converted to {docx_path.name}")
            return True
        except Exception as e:
            self.logger.error(f"Error converting {pdf_path.name}: {str(e)}")
            return False
    
    def convert_all_pdfs(self, folder: Path, court: str, rulings: List[str],
                         ruling_dates: Optional[dict] = None, progress_callback=None) -> List[Tuple[str, str, str]]:
        """
        Convert all PDF files in folder to DOCX and rename them
        
        Args:
            folder: Folder containing PDF files
            court: Court name ("ALLCUS_HQ" or "ALLCUS_NY")
            rulings: List of ruling numbers (e.g., ["HQ H350894", "NY N357085"])
        
        Returns:
            List of tuples: (docket_number, filename, url)
        """
        converted_files = []
        
        # Get all PDF files in folder
        pdf_files = list(folder.glob("*.pdf"))
        
        if not pdf_files:
            self.logger.warning("No PDF files found in folder")
            return converted_files
        
        # Create a mapping of docket numbers to rulings for filename generation
        docket_to_ruling = {}
        for ruling in rulings:
            docket = self.extract_docket_number(ruling)
            docket_to_ruling[docket] = ruling
        
        # Process each PDF
        total_files = len(pdf_files)
        processed_files = 0
        for pdf_file in pdf_files:
            try:
                # Try to match PDF to a ruling by checking if docket number is in filename
                # PDFs might be downloaded with various names, so we'll try to extract docket
                pdf_name = pdf_file.stem.upper()
                matched_docket = None
                
                # Try to find matching docket in filename
                for docket in docket_to_ruling.keys():
                    if docket.upper() in pdf_name or docket.upper().replace(" ", "") in pdf_name:
                        matched_docket = docket
                        break
                
                # If no match found, try to extract from filename
                if not matched_docket:
                    # Try common patterns
                    for part in pdf_name.split():
                        if part in docket_to_ruling:
                            matched_docket = part
                            break
                
                # If still no match, use first available docket (fallback)
                if not matched_docket and docket_to_ruling:
                    matched_docket = list(docket_to_ruling.keys())[0]
                    self.logger.warning(f"Could not match PDF {pdf_file.name} to a ruling, using fallback docket")
                
                if not matched_docket:
                    self.logger.warning(f"Skipping {pdf_file.name}: no matching docket found")
                    continue
                
                # Generate new filename using ruling date if available
                date_str = ""
                if ruling_dates and matched_docket in ruling_dates:
                    date_str = ruling_dates[matched_docket].strip()
                new_filename = self.generate_filename(matched_docket, court, date_str)
                docx_path = folder / new_filename
                
                # Convert PDF to DOCX
                if self.convert_pdf_to_docx(pdf_file, docx_path):
                    # Delete original PDF
                    try:
                        pdf_file.unlink()
                        self.logger.info(f"Deleted original PDF: {pdf_file.name}")
                    except Exception as e:
                        self.logger.warning(f"Could not delete PDF {pdf_file.name}: {str(e)}")
                    
                    # Generate URL
                    url = f"https://rulings.cbp.gov/ruling/{matched_docket}"
                    
                    converted_files.append((matched_docket, new_filename, url))
                else:
                    self.logger.error(f"Failed to convert {pdf_file.name}")
                    
            except Exception as e:
                self.logger.error(f"Error processing {pdf_file.name}: {str(e)}")
                continue
            finally:
                processed_files += 1
                if progress_callback:
                    try:
                        progress_callback(processed_files, total_files)
                    except Exception:
                        pass
        
        self.logger.info(f"Converted {len(converted_files)} PDF files to DOCX")
        return converted_files

