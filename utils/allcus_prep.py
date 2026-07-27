"""
Directory Preparation Module for ALLCUS RPA
Creates folder structure in user's Downloads directory
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Tuple


def get_downloads_path() -> Path:
    """Get user's Downloads directory path"""
    return Path.home() / "Downloads"


def create_directory_structure(court: str) -> Tuple[Path, Path]:
    """
    Create directory structure for ALLCUS collections
    
    Args:
        court: Either "ALLCUS_HQ" or "ALLCUS_NY"
    
    Returns:
        Tuple of (base_path, run_folder_path)
    """
    downloads = get_downloads_path()
    base_folder = downloads / "ALLCUS Collections"
    
    # Create main folder if it doesn't exist
    base_folder.mkdir(exist_ok=True)
    
    # Create court subfolders
    hq_folder = base_folder / "ALLCUS HQ"
    ny_folder = base_folder / "ALLCUS NY"
    hq_folder.mkdir(exist_ok=True)
    ny_folder.mkdir(exist_ok=True)
    
    # Determine which court folder to use
    if court == "ALLCUS_HQ":
        court_folder = hq_folder
        court_prefix = "HQ"
    elif court == "ALLCUS_NY":
        court_folder = ny_folder
        court_prefix = "NY"
    else:
        raise ValueError(f"Invalid court: {court}. Must be 'ALLCUS_HQ' or 'ALLCUS_NY'")
    
    # Create run subfolder with datetime
    now = datetime.now()
    # Format: COURT_HH-MM-SS_MM-DD-YYYY (12-hour format)
    time_str = now.strftime("%I-%M-%S")  # 12-hour format
    date_str = now.strftime("%m-%d-%Y")
    run_folder_name = f"{court_prefix}_{time_str}_{date_str}"
    run_folder = court_folder / run_folder_name
    run_folder.mkdir(exist_ok=True)
    
    return base_folder, run_folder

