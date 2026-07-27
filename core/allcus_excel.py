"""
Excel Report Generation Module for ALLCUS RPA
Creates Excel reports with document information
"""

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, GradientFill
from pathlib import Path
from datetime import datetime
from typing import List, Tuple


class ALLCUSExcelGenerator:
    """Excel report generator for ALLCUS documents"""
    
    def __init__(self, logger):
        """
        Initialize Excel generator
        
        Args:
            logger: ALLCUSLogger instance
        """
        self.logger = logger
    
    def generate_report(self, folder: Path, court: str, converted_files: List[Tuple[str, str, str]]) -> Path:
        """
        Generate Excel report with document information
        
        Args:
            folder: Folder where report should be saved
            court: Court name ("ALLCUS_HQ" or "ALLCUS_NY")
            converted_files: List of tuples (docket_number, filename, url)
        
        Returns:
            Path to generated Excel file
        """
        try:
            # Determine court prefix
            if court == "ALLCUS_HQ":
                court_prefix = "HQ"
            elif court == "ALLCUS_NY":
                court_prefix = "NY"
            else:
                court_prefix = court
            
            # Prepare data
            data = {
                "COURT": [],
                "DOCKET NUMBER": [],
                "FILENAME": [],
                "URL": []
            }
            
            for docket_number, filename, url in converted_files:
                data["COURT"].append(court_prefix)
                data["DOCKET NUMBER"].append(docket_number)
                data["FILENAME"].append(filename)
                data["URL"].append(url)
            
            # Create DataFrame
            df = pd.DataFrame(data)
            
            # Generate report filename: COURT-REPORT_HH-MM-SS_MM-DD-YYYY.xlsx
            now = datetime.now()
            time_str = now.strftime("%I-%M-%S")  # 12-hour format
            date_str = now.strftime("%m-%d-%Y")
            report_filename = f"{court_prefix}-REPORT_{time_str}_{date_str}.xlsx"
            report_path = folder / report_filename
            
            # Save to Excel
            df.to_excel(report_path, index=False, engine='openpyxl')

            # Auto-fit column widths and center-align cells
            workbook = load_workbook(report_path)
            worksheet = workbook.active
            center_align = Alignment(horizontal="center", vertical="center")
            header_fill = GradientFill(type="linear", degree=0, stop=("FF833AB4", "FFFD1D1D"))
            header_font = Font(color="FFFFFF", bold=True)
            for column_cells in worksheet.columns:
                max_length = 0
                for cell in column_cells:
                    value = cell.value
                    cell.alignment = center_align
                    if cell.row == 1:
                        cell.fill = header_fill
                        cell.font = header_font
                    if value is None:
                        continue
                    max_length = max(max_length, len(str(value)))
                column_letter = column_cells[0].column_letter
                worksheet.column_dimensions[column_letter].width = max(12, max_length + 2)
            workbook.save(report_path)
            
            self.logger.info(f"Excel report generated: {report_filename}")
            self.logger.info(f"Report contains {len(converted_files)} documents")
            
            return report_path
            
        except Exception as e:
            self.logger.error(f"Error generating Excel report: {str(e)}")
            raise

