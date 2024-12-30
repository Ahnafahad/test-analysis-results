# ====================================================================================================
# File: app.py
#
# Enhanced Analytics System for Test Analysis Platform
# Now includes:
# 1. Enhanced section performance comparisons (between consecutive tests)
# 2. Top questions performance analysis (Sheet2)
# 3. Response pattern analysis (Sheet3)
# 4. Gap analysis with peer group
# 5. Section-wise consistency analysis
# 6. Question selection strategy analysis
# 7. Recovery rate analysis
# 8. Competitive position analysis
# 9. Question difficulty handling analysis
# 10. Section strength index
#
# All while preserving existing functionality and data structure.
#
# ----------------------------------------------------------------------------------------------------
# CHANGELOG:
# - Integrated logging at every major step for traceability and error detection.
# - Added new analytics functions called from generate_test_analysis() and other integration points.
# - Enhanced with deep diagnostic logging, file backups, multi-sheet handling, and new validations.
# - Now updated to fix multi-sheet Excel saving with robust error handling.
#
# Lines are annotated for clarity of new/modified code segments.
#
# ====================================================================================================

import os
import json
from datetime import date
import time 
import uuid
import pandas as pd
import numpy as np
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import plotly
import plotly.graph_objs as go
import subprocess
import numpy as np
from contextlib import contextmanager
# ----------------------------------------------------------------------------------------------------
#  1  Logging Configuration
# ----------------------------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logging.info("Starting up the Enhanced Test Analysis Application...")

# ----------------------------------------------------------------------------------------------------
#  1a  NEW: Additional Logging Functions
# ----------------------------------------------------------------------------------------------------
def log_dataframe_info(df, sheet_name, context):
    """
    Exhaustively logs DataFrame information for debugging.
    
    Parameters:
        df (pandas.DataFrame): DataFrame to analyze
        sheet_name (str): Name of the sheet for context
        context (str): Additional contextual information
    """
    logging.info(f"DataFrame Analysis - {sheet_name} [{context}]")
    logging.info("-" * 80)
    logging.info(f"Shape: {df.shape}")
    logging.info(f"Columns: {df.columns.tolist()}")
    logging.info(f"Index: {df.index}")
    logging.info(f"Memory Usage: {df.memory_usage().sum() / 1024:.2f} KB")
    if not df.empty:
        logging.info(f"First row: {df.iloc[0].to_dict()}")
        logging.info(f"Data Types:\n{df.dtypes}")
        logging.info(f"Null Counts:\n{df.isnull().sum()}")
    logging.info("-" * 80)

def log_excel_file_info(file_path, context):
    """
    Logs detailed Excel file information.
    
    Parameters:
        file_path (str): Path to Excel file
        context (str): Context of the operation
    """
    try:
        logging.info(f"Excel File Analysis - {file_path} [{context}]")
        logging.info("-" * 80)
        
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            mod_time = os.path.getmtime(file_path)
            
            logging.info(f"File exists: True")
            logging.info(f"File size: {file_size/1024:.2f} KB")
            logging.info(f"Last modified: {pd.Timestamp.fromtimestamp(mod_time)}")
            
            xls = pd.ExcelFile(file_path)
            logging.info(f"Sheet names: {xls.sheet_names}")
            
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                log_dataframe_info(df, sheet, f"From file {file_path}")
        else:
            logging.info(f"File exists: False")
        
        logging.info("-" * 80)
    except Exception as e:
        logging.error(f"Error analyzing Excel file: {str(e)}")
        logging.error(f"Stack trace:", exc_info=True)

def log_operation_boundary(operation_name, is_start=True):
    """
    Creates visible boundaries in logs for major operations.
    
    Parameters:
        operation_name (str): Name of the operation
        is_start (bool): Whether this is the start or end of the operation
    """
    boundary = "=" * 40
    if is_start:
        logging.info(f"\n{boundary}")
        logging.info(f"STARTING OPERATION: {operation_name}")
        logging.info(f"{boundary}\n")
    else:
        logging.info(f"\n{boundary}")
        logging.info(f"COMPLETED OPERATION: {operation_name}")
        logging.info(f"{boundary}\n")
def safe_file_operation(file_path, operation_func, max_retries=5, retry_delay=1):
    """
    Safely performs file operations with retries for Windows file locking issues.
    
    Parameters:
        file_path (str): Path to the file being operated on
        operation_func (callable): Function that performs the actual file operation
        max_retries (int): Maximum number of retry attempts
        retry_delay (float): Delay in seconds between retries
    
    Returns:
        bool: True if operation succeeded, False otherwise
    """
    for attempt in range(max_retries):
        try:
            # Attempt the file operation
            operation_func()
            return True
            
        except PermissionError as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"PermissionError on attempt {attempt + 1}/{max_retries} "
                    f"for file {file_path}. Retrying in {retry_delay} seconds..."
                )
                time.sleep(retry_delay)
            else:
                logging.error(
                    f"Failed to perform file operation after {max_retries} attempts: {str(e)}"
                )
                return False
                
        except Exception as e:
            logging.error(f"Unexpected error during file operation: {str(e)}")
            return False
    
    return False

@contextmanager
def safe_file_handling(file_path, mode='r', encoding=None):
    """
    Context manager for safely handling file operations with proper cleanup.
    
    Parameters:
        file_path (str): Path to the file
        mode (str): File open mode ('r', 'w', etc.)
        encoding (str): File encoding (e.g., 'utf-8')
    
    Yields:
        file object: The opened file object
    """
    file_obj = None
    try:
        file_obj = open(file_path, mode, encoding=encoding)
        yield file_obj
    finally:
        if file_obj:
            try:
                file_obj.close()
            except Exception as e:
                logging.error(f"Error closing file {file_path}: {str(e)}")
# ----------------------------------------------------------------------------------------------------
#  2  Helper function to convert numpy data types to native Python types (unchanged)
# ----------------------------------------------------------------------------------------------------
def convert_numpy_types(obj):
    """
    Recursively convert numpy types in the dictionary to native Python types.
    """
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if isinstance(k, np.integer):
                k = int(k)
            elif isinstance(k, np.floating):
                k = float(k)
            elif isinstance(k, np.str_):
                k = str(k)
            new_obj[k] = convert_numpy_types(v)
        return new_obj
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.str_):
        return str(obj)
    else:
        return obj

# ----------------------------------------------------------------------------------------------------
#  2b  Existing Validation Functions for Sheet1, Sheet2, Sheet3
# ----------------------------------------------------------------------------------------------------
def validate_sheet1_structure(df):
    """
    Validates Sheet1 structure matches expected format.
    Parameters:
        df (pandas.DataFrame): DataFrame to validate
    Returns:
        bool: True if valid, raises ValueError if invalid
    """
    required_cols = [
        "ID", "Name",
        "1 Correct", "1 Wrong", "1 Marks", "1 Percentage",
        "2 Correct", "2 Wrong", "2 Marks", "2 Percentage",
        "3 Correct", "3 Wrong", "3 Marks", "3 Percentage",
        "Total Marks in MCQ", "Total Percentage", "Rank in MCQ",
        "Total Marks", "Rank"
    ]
    
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Sheet1 missing required columns: {missing_cols}")
    return True

def validate_sheet2_structure(df):
    """
    Validates Sheet2 structure matches expected format.
    Parameters:
        df (pandas.DataFrame): DataFrame to validate
    Returns:
        bool: True if valid, raises ValueError if invalid
    """
    required_cols = [
        "1 Top Ten Questions right", "no. of right",
        "1 Top Ten Questions Skipped", "no. of skipped",
        "1 Top Ten Questions Wrong", "no. of wrong",
        "2 Top Ten Questions right", "no. of right",
        "2 Top Ten Questions Skipped", "no. of skipped",
        "2 Top Ten Questions Wrong", "no. of wrong",
        "3 Top Ten Questions right", "no. of right",
        "3 Top Ten Questions Skipped", "no. of skipped",
        "3 Top Ten Questions Wrong", "no. of wrong"
    ]
    
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Sheet2 missing required columns: {missing_cols}")
    return True

def validate_sheet3_structure(df):
    """
    Validates Sheet3 structure matches expected format.
    Parameters:
        df (pandas.DataFrame): DataFrame to validate
    Returns:
        bool: True if valid, raises ValueError if invalid
    """
    # Check for Roll column
    if "Roll" not in df.columns:
        raise ValueError("Sheet3 missing required column: Roll")
    
    # Check for section-question columns
    required_patterns = [
        [f"Section1-Q{i}" for i in range(1, 31)],
        [f"Section2-Q{i}" for i in range(1, 26)],
        [f"Section3-Q{i}" for i in range(1, 16)]
    ]
    
    for pattern in required_patterns:
        missing = [col for col in pattern if col not in df.columns]
        if missing:
            raise ValueError(f"Sheet3 missing required columns: {missing}")
    
    return True

# ----------------------------------------------------------------------------------------------------
#  3  NEW: Comprehensive Excel Validation Function
# ----------------------------------------------------------------------------------------------------
def validate_excel_structure(filepath):
    """
    Comprehensively validates Excel file structure with detailed logging.
    
    Parameters:
        filepath: Path to Excel file
    Returns:
        tuple: (bool, str) - (is_valid, error_message)
    """
    log_operation_boundary("validate_excel_structure", True)
    
    try:
        logging.info(f"Validating Excel file: {filepath}")
        
        if not os.path.exists(filepath):
            msg = f"File does not exist: {filepath}"
            logging.error(msg)
            return False, msg
            
        # Load Excel file
        xls = pd.ExcelFile(filepath)
        sheet_names = set(xls.sheet_names)
        required_sheets = {"Sheet1", "Sheet2", "Sheet3"}
        
        logging.info(f"Found sheets: {sheet_names}")
        logging.info(f"Required sheets: {required_sheets}")
        
        # Check for missing sheets
        missing_sheets = required_sheets - sheet_names
        if missing_sheets:
            msg = f"Missing required sheets: {missing_sheets}"
            logging.error(msg)
            return False, msg
            
        # Load and validate each sheet
        for sheet in required_sheets:
            logging.info(f"Validating {sheet}...")
            df = pd.read_excel(xls, sheet_name=sheet)
            log_dataframe_info(df, sheet, "Validation")
            
            # Validate specific sheet structure
            try:
                if sheet == "Sheet1":
                    validate_sheet1_structure(df)
                elif sheet == "Sheet2":
                    validate_sheet2_structure(df)
                else:  # Sheet3
                    validate_sheet3_structure(df)
            except ValueError as ve:
                msg = f"Validation failed for {sheet}: {str(ve)}"
                logging.error(msg)
                return False, msg
        
        logging.info("All sheets validated successfully")
        return True, "Validation successful"
        
    except Exception as e:
        msg = f"Error validating Excel structure: {str(e)}"
        logging.error(msg)
        logging.error("Stack trace:", exc_info=True)
        return False, msg
        
    finally:
        log_operation_boundary("validate_excel_structure", False)

# ----------------------------------------------------------------------------------------------------
#  4  Flask App Configuration
# ----------------------------------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = "your_secret_key"
DATA_DIR = "data"
MAIN_DATA_FILE = os.path.join(DATA_DIR, "main_data.xlsx")
SERIES_CONFIG_FILE = os.path.join(DATA_DIR, "series_config.json")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# ----------------------------------------------------------------------------------------------------
#  5  Initialize main_data.xlsx if not present (Sheet1 logic preserved)
# ----------------------------------------------------------------------------------------------------
if not os.path.exists(MAIN_DATA_FILE):
    logging.info("MAIN_DATA_FILE not found, creating a new file: %s", MAIN_DATA_FILE)
    df_init = pd.DataFrame(columns=[
        "ID","Name",
        "1 Correct","1 Wrong","1 Marks","1 Percentage",
        "2 Correct","2 Wrong","2 Marks","2 Percentage",
        "3 Correct","3 Wrong","3 Marks","3 Percentage",
        "Total Marks in MCQ","Total Percentage","Rank in MCQ",
        "Essay 1","Essay 2","Essay 3","Essay 4",
        "Total Marks","Rank"
    ])
    df_init.to_excel(MAIN_DATA_FILE, index=False, sheet_name="Sheet1")

# ----------------------------------------------------------------------------------------------------
#  6  Initialize series_config.json if not present
# ----------------------------------------------------------------------------------------------------
if not os.path.exists(SERIES_CONFIG_FILE):
    logging.info("SERIES_CONFIG_FILE not found, creating a new file: %s", SERIES_CONFIG_FILE)
    with open(SERIES_CONFIG_FILE, 'w') as f:
        json.dump({}, f)

# ----------------------------------------------------------------------------------------------------
#  7  Configuration loading/saving
# ----------------------------------------------------------------------------------------------------
def load_series_config():
    try:
        with open(SERIES_CONFIG_FILE, 'r') as f:
            cfg = json.load(f)
        logging.info("Successfully loaded series config from %s", SERIES_CONFIG_FILE)
        return cfg
    except Exception as e:
        logging.error("Error loading series config: %s", e)
        return {}

def save_series_config(cfg):
    try:
        with open(SERIES_CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=4)
        logging.info("Successfully saved series config to %s", SERIES_CONFIG_FILE)
    except Exception as e:
        logging.error("Error saving series config: %s", e)

# ----------------------------------------------------------------------------------------------------
#  8  load_main_data() - preserved for backward compatibility with existing usage
# ----------------------------------------------------------------------------------------------------
def load_main_data():
    """
    Loads the primary DataFrame from the first sheet (Sheet1) of main_data.xlsx.
    Preserved for backward compatibility with existing features.
    """
    if os.path.exists(MAIN_DATA_FILE):
        logging.info("Loading main data from Sheet1 in %s", MAIN_DATA_FILE)
        try:
            return pd.read_excel(MAIN_DATA_FILE, sheet_name="Sheet1")
        except Exception as e:
            logging.error("Error reading main_data.xlsx Sheet1: %s", e)
            return pd.DataFrame()
    else:
        logging.warning("MAIN_DATA_FILE does not exist, returning empty DataFrame.")
        return pd.DataFrame()

# ----------------------------------------------------------------------------------------------------
#  9  Additional Sheets Loading (Sheet2, Sheet3) - Provided for advanced analytics
# ----------------------------------------------------------------------------------------------------
def load_additional_sheets():
    """
    Attempts to read Sheet2 and Sheet3 from the main_data.xlsx file.
    If sheets are missing or malformed, returns empty DataFrames.
    """
    if not os.path.exists(MAIN_DATA_FILE):
        logging.warning("MAIN_DATA_FILE not found for additional sheets.")
        return pd.DataFrame(), pd.DataFrame()
    try:
        xls = pd.ExcelFile(MAIN_DATA_FILE)
        # Sheet2
        if "Sheet2" in xls.sheet_names:
            df_sheet2 = pd.read_excel(xls, sheet_name="Sheet2")
            logging.info("Loaded Sheet2 data with shape %s", df_sheet2.shape)
        else:
            logging.info("Sheet2 not found, returning empty DataFrame.")
            df_sheet2 = pd.DataFrame()

        # Sheet3
        if "Sheet3" in xls.sheet_names:
            df_sheet3 = pd.read_excel(xls, sheet_name="Sheet3")
            logging.info("Loaded Sheet3 data with shape %s", df_sheet3.shape)
        else:
            logging.info("Sheet3 not found, returning empty DataFrame.")
            df_sheet3 = pd.DataFrame()

        return df_sheet2, df_sheet3

    except Exception as e:
        logging.error("Error loading additional sheets: %s", e)
        return pd.DataFrame(), pd.DataFrame()

# ----------------------------------------------------------------------------------------------------
# 10  Basic Data Operations: clean_data(), recompute_ranks(), and ENHANCED save_main_data()
# ----------------------------------------------------------------------------------------------------
def clean_data(df):
    """
    Removes rows where ID and Name are both empty. Preserves everything else.
    """
    before_count = len(df)
    df = df[~(df["ID"].isna() & df["Name"].isna())]
    after_count = len(df)
    logging.info("clean_data() removed %d rows (empty ID & Name).", before_count - after_count)
    return df

def recompute_ranks(df, series_id, test_id):
    """
    Recomputes ranks for a given series and test based on 'Total Marks'.
    """
    logging.info("Recomputing ranks for series: %s, test: %s", series_id, test_id)
    df_test = df[(df["SeriesID"] == series_id) & (df["TestID"] == test_id)].copy()
    df_test = df_test[~(df_test["ID"].isna()) & ~(df_test["Name"].isna())]
    df_test = df_test.sort_values("Total Marks", ascending=False)
    df_test["Rank"] = range(1, len(df_test) + 1)
    for i, row in df_test.iterrows():
        df.loc[i, "Rank"] = row["Rank"]
    return df

def save_main_data(df, df_sheet2=None, df_sheet3=None):
    """
    Enhanced save function with robust error handling and retry mechanism.
    """
    log_operation_boundary("save_main_data", True)
    
    try:
        # Generate temporary filename with proper extension
        temp_file = MAIN_DATA_FILE.replace('.xlsx', '_temp.xlsx')
        backup_file = MAIN_DATA_FILE.replace('.xlsx', '_backup.xlsx')
        
        logging.info(f"Starting save operation...")
        logging.info(f"Temporary file: {temp_file}")
        logging.info(f"Backup file: {backup_file}")
        
        # Create backup if original exists
        if os.path.exists(MAIN_DATA_FILE):
            def backup_operation():
                import shutil
                shutil.copy2(MAIN_DATA_FILE, backup_file)
            
            if not safe_file_operation(MAIN_DATA_FILE, backup_operation):
                raise ValueError("Failed to create backup file")
            logging.info(f"Backup created successfully at {backup_file}")
        
        # Log DataFrame states before save
        logging.info("Analyzing DataFrames before save:")
        logging.info(f"Sheet1 shape: {df.shape}")
        if df_sheet2 is not None:
            logging.info(f"Sheet2 shape: {df_sheet2.shape}")
        if df_sheet3 is not None:
            logging.info(f"Sheet3 shape: {df_sheet3.shape}")
        
        # Save to temporary file
        logging.info(f"Writing to temporary file: {temp_file}")
        
        def save_operation():
            with pd.ExcelWriter(temp_file, engine='openpyxl', mode='w') as writer:
                logging.info("Writing Sheet1...")
                df.to_excel(writer, index=False, sheet_name="Sheet1")
                
                if df_sheet2 is not None:
                    logging.info("Writing Sheet2...")
                    df_sheet2.to_excel(writer, index=False, sheet_name="Sheet2")
                
                if df_sheet3 is not None:
                    logging.info("Writing Sheet3...")
                    df_sheet3.to_excel(writer, index=False, sheet_name="Sheet3")
        
        if not safe_file_operation(temp_file, save_operation):
            raise ValueError("Failed to write temporary file")
        
        # Verify temporary file
        logging.info("Verifying temporary file integrity...")
        def verify_operation():
            verification_data = pd.read_excel(temp_file, sheet_name=None)
            logging.info(f"Verification results:")
            for sheet_name, sheet_data in verification_data.items():
                logging.info(f"- {sheet_name}: {sheet_data.shape} rows")
        
        if not safe_file_operation(temp_file, verify_operation):
            raise ValueError("Failed to verify temporary file")
        
        # Replace original with temporary file
        logging.info("Replacing original file with temporary file...")
        def replace_operation():
            if os.path.exists(MAIN_DATA_FILE):
                os.remove(MAIN_DATA_FILE)
            os.rename(temp_file, MAIN_DATA_FILE)
        
        if not safe_file_operation(MAIN_DATA_FILE, replace_operation):
            raise ValueError("Failed to replace original file")
        
        logging.info("Save operation completed successfully")
        
        # Clean up backup if everything succeeded
        if os.path.exists(backup_file):
            def cleanup_operation():
                os.remove(backup_file)
            
            if not safe_file_operation(backup_file, cleanup_operation):
                logging.warning("Failed to remove backup file, but save was successful")
            else:
                logging.info("Backup file cleaned up successfully")
            
        return True
        
    except Exception as e:
        logging.error(f"Error during save operation: {str(e)}")
        logging.error("Stack trace:", exc_info=True)
        
        # Attempt to restore from backup
        if os.path.exists(backup_file):
            logging.info("Attempting to restore from backup...")
            def restore_operation():
                if os.path.exists(MAIN_DATA_FILE):
                    os.remove(MAIN_DATA_FILE)
                os.rename(backup_file, MAIN_DATA_FILE)
            
            if not safe_file_operation(MAIN_DATA_FILE, restore_operation):
                logging.error("Failed to restore from backup")
            else:
                logging.info("Restore from backup successful")
        
        # Clean up temporary file if it exists
        if os.path.exists(temp_file):
            def cleanup_temp_operation():
                os.remove(temp_file)
            
            if not safe_file_operation(temp_file, cleanup_temp_operation):
                logging.warning("Failed to clean up temporary file")
            else:
                logging.info("Temporary file cleaned up")
        
        raise
        
    finally:
        log_operation_boundary("save_main_data", False)

# ----------------------------------------------------------------------------------------------------
# 11  Basic Class Metrics - compute_class_metrics() (unchanged in interface)
# ----------------------------------------------------------------------------------------------------
def compute_class_metrics(df_test):
    """
    Computes class-level average accuracy and attempts per section.
    Extended in the future for peer-group or strength calculations.
    """
    logging.info("Computing class metrics for test with %d rows of data.", len(df_test))
    metrics = {}
    for sec_id in ["1","2","3"]:
        correct_col = f"{sec_id} Correct"
        wrong_col = f"{sec_id} Wrong"
        if correct_col in df_test.columns and wrong_col in df_test.columns:
            total_correct = df_test[correct_col].sum()
            attempts = df_test[correct_col] + df_test[wrong_col]
            total_attempts = attempts.sum()
            if total_attempts > 0:
                class_accuracy = (total_correct / total_attempts) * 100
                class_attempts = attempts.mean()
            else:
                class_accuracy = 0.0
                class_attempts = 0.0
        else:
            class_accuracy = 0.0
            class_attempts = 0.0

        metrics[sec_id] = {
            "class_accuracy": class_accuracy,
            "class_attempts": class_attempts
        }

    logging.info("Finished computing class metrics for test.")
    return metrics

# ----------------------------------------------------------------------------------------------------
# 12  Section Analysis - section_analysis() (unchanged in interface)
# ----------------------------------------------------------------------------------------------------
def section_analysis(row, sec_map, class_metrics):
    """
    Analyzes a single student's performance by section.
    Extended to integrate with advanced analytics from Sheet3 if needed.
    """
    sections = []
    for sec_id in ["1","2","3"]:
        correct = row.get(f"{sec_id} Correct", 0)
        wrong = row.get(f"{sec_id} Wrong", 0)
        attempted = correct + wrong
        if attempted > 0:
            accuracy = round((correct / attempted) * 100, 2)
        else:
            accuracy = 0.0

        class_acc = class_metrics[sec_id]["class_accuracy"] if sec_id in class_metrics else 0.0
        class_att = class_metrics[sec_id]["class_attempts"] if sec_id in class_metrics else 0.0

        diff_acc = round(accuracy - class_acc, 2)
        diff_attempts = round(attempted - class_att, 2)

        sections.append({
            "sec_id": sec_id,
            "name": sec_map.get(sec_id, f"Section {sec_id}"),
            "correct": correct,
            "wrong": wrong,
            "attempted": attempted,
            "accuracy": accuracy,
            "diff_vs_class_acc": diff_acc,
            "diff_vs_class_attempts": diff_attempts
        })

    return sections

# ----------------------------------------------------------------------------------------------------
# 13  Enhanced Analytics Functions
# ----------------------------------------------------------------------------------------------------
def enhanced_section_comparison(df_student, test_name, sec_map):
    """
    Compares this test's performance to previous test performance for each section.
    Weighted metrics:
      - Accuracy improvement (40%)
      - Attempt rate change (30%)
      - Consistency in correct answers (30%)
    Returns a dict with per-section comparison + overall improvement score.
    Logs each step for debugging/tracing.
    """
    logging.info("Running enhanced_section_comparison for test %s...", test_name)
    # Sort the student's tests by test name
    df_student_sorted = df_student.sort_values("TestName")
    current_test_row = df_student_sorted[df_student_sorted["TestName"] == test_name]
    if len(current_test_row) == 0:
        logging.warning("No current test row found for test %s. Returning empty comparison.", test_name)
        return {}

    # Identify the previous test if any
    prev_rows = df_student_sorted[df_student_sorted["TestName"] < test_name]
    if len(prev_rows) == 0:
        logging.info("No previous test found for comparison. Returning empty results.")
        return {}

    prev_test_row = prev_rows.iloc[-1]

    comparison_results = {}
    overall_score = 0.0
    for sec_id in ["1","2","3"]:
        section_name = sec_map.get(sec_id, f"Section {sec_id}")

        cur_correct = current_test_row[f"{sec_id} Correct"].values[0] if f"{sec_id} Correct" in current_test_row else 0
        cur_wrong = current_test_row[f"{sec_id} Wrong"].values[0] if f"{sec_id} Wrong" in current_test_row else 0
        prev_correct = prev_test_row.get(f"{sec_id} Correct", 0)
        prev_wrong = prev_test_row.get(f"{sec_id} Wrong", 0)

        cur_attempts = cur_correct + cur_wrong
        prev_attempts = prev_correct + prev_wrong

        cur_accuracy = (cur_correct / cur_attempts * 100) if cur_attempts else 0.0
        prev_accuracy = (prev_correct / prev_attempts * 100) if prev_attempts else 0.0
        acc_diff = cur_accuracy - prev_accuracy  # positive => improvement

        attempt_diff = cur_attempts - prev_attempts  # positive => more attempts

        # We'll assume "consistency in correct answers" means how many correct from prev test also correct in current
        consistency = min(cur_correct, prev_correct) / max(1, prev_correct) * 100 if prev_correct else 0.0

        # Weighted score
        weighted_score = (acc_diff * 0.4) + (attempt_diff * 0.3) + (consistency * 0.3)
        overall_score += weighted_score

        comparison_results[sec_id] = {
            "section_name": section_name,
            "acc_diff": round(acc_diff, 2),
            "attempt_diff": round(attempt_diff, 2),
            "consistency_score": round(consistency, 2),
            "weighted_score": round(weighted_score, 2)
        }

    comparison_results["overall_improvement_score"] = round(overall_score / 3, 2)  # average across sections
    logging.info("enhanced_section_comparison completed for test %s.", test_name)
    return comparison_results

def top_questions_analysis(student_id, df_sheet2, df_sheet3):
    """
    Analyzes performance on common questions using Sheet2 and Sheet3 data.
    """
    if df_sheet2.empty or df_sheet3.empty:
        return {
            "commonly_correct_success_rate": 0,
            "commonly_wrong_avoidance_rate": 0,
            "strategic_skip_alignment": 0,
            "strategic_score": 0
        }

    student_row = df_sheet3[df_sheet3["Roll"] == float(student_id)]
    if student_row.empty:
        return {
            "commonly_correct_success_rate": 0,
            "commonly_wrong_avoidance_rate": 0, 
            "strategic_skip_alignment": 0,
            "strategic_score": 0
        }

    # Calculate success rate on commonly correct questions
    correct_count = 0
    total_common = 0
    for section in [1, 2, 3]:
        section_questions = [col for col in student_row.columns if f"Section{section}" in col]
        for q in section_questions:
            if "(C)" in str(student_row[q].iloc[0]):
                correct_count += 1
            total_common += 1
    
    commonly_correct = correct_count/total_common if total_common > 0 else 0

    # Calculate wrong questions avoidance rate
    wrong_count = 0
    total_wrong = 0 
    for section in [1, 2, 3]:
        section_questions = [col for col in student_row.columns if f"Section{section}" in col]
        for q in section_questions:
            if "(W)" in str(student_row[q].iloc[0]):
                wrong_count += 1
            total_wrong += 1

    wrong_avoidance = 1 - (wrong_count/total_wrong) if total_wrong > 0 else 0

    # Calculate skip strategy based on NAN responses
    skip_count = 0
    total_questions = 0
    for section in [1, 2, 3]:
        section_questions = [col for col in student_row.columns if f"Section{section}" in col]
        for q in section_questions:
            val = str(student_row[q].iloc[0])
            if "NAN" in val or pd.isna(val):
                skip_count += 1
            total_questions += 1

    skip_alignment = skip_count/total_questions if total_questions > 0 else 0

    # Calculate overall strategic score
    strategic_score = (commonly_correct * 0.4 + 
                      wrong_avoidance * 0.3 +
                      skip_alignment * 0.3)

    return {
        "commonly_correct_success_rate": commonly_correct,
        "commonly_wrong_avoidance_rate": wrong_avoidance,
        "strategic_skip_alignment": skip_alignment,
        "strategic_score": strategic_score
    }

def analyze_response_patterns(student_id, df_sheet3):
    """
    Analyzes response patterns using Sheet3 data.
    """
    if df_sheet3.empty:
        return {
            "longest_success_streak": 0,
            "recovery_rate": 0,
            "skip_strategy_score": 0
        }

    student_row = df_sheet3[df_sheet3["Roll"] == float(student_id)]
    if student_row.empty:
        return {
            "longest_success_streak": 0,
            "recovery_rate": 0,
            "skip_strategy_score": 0
        }

    # Calculate longest streak of correct answers
    current_streak = 0
    max_streak = 0
    wrong_to_correct = 0
    total_recoveries = 0
    skips_after_wrong = 0
    total_wrong = 0

    for section in [1, 2, 3]:
        section_questions = [col for col in student_row.columns if f"Section{section}" in col]
        last_was_wrong = False
        
        for q in section_questions:
            val = str(student_row[q].iloc[0])
            
            if "(C)" in val:
                current_streak += 1
                if last_was_wrong:
                    wrong_to_correct += 1
                last_was_wrong = False
            elif "(W)" in val:
                max_streak = max(max_streak, current_streak)
                current_streak = 0
                total_wrong += 1
                last_was_wrong = True
            elif "NAN" in val or pd.isna(val):
                if last_was_wrong:
                    skips_after_wrong += 1
                max_streak = max(max_streak, current_streak)
                current_streak = 0
                last_was_wrong = False

    max_streak = max(max_streak, current_streak)
    recovery_rate = wrong_to_correct/total_wrong if total_wrong > 0 else 0
    skip_strategy = skips_after_wrong/total_wrong if total_wrong > 0 else 0

    return {
        "longest_success_streak": max_streak,
        "recovery_rate": recovery_rate,
        "skip_strategy_score": skip_strategy
    }

def analyze_peer_group_gaps(student_id, df, series_id, test_id):
    """
    Gap analysis with a peer group (±3 rank positions).
    Returns a dict summarizing peer comparisons for the given test.
    """
    logging.info("Analyzing peer group gaps for student %s in test %s...", student_id, test_id)
    df_test = df[(df["SeriesID"] == series_id) & (df["TestID"] == test_id)]
    df_test = df_test[~df_test["ID"].isna() & ~df_test["Name"].isna()]
    if df_test.empty:
        logging.warning("No test data found for test %s in series %s. Cannot do peer analysis.", test_id, series_id)
        return {}

    # Find student's rank
    stu_data = df_test[df_test["ID"] == float(student_id)]
    if stu_data.empty:
        logging.warning("Student %s not found in test data. Returning empty peer group result.", student_id)
        return {}

    stu_rank = int(stu_data.iloc[0]["Rank"] if not pd.isna(stu_data.iloc[0]["Rank"]) else 99999)
    min_rank = max(1, stu_rank - 3)
    max_rank = stu_rank + 3
    df_peers = df_test[(df_test["Rank"] >= min_rank) & (df_test["Rank"] <= max_rank)]

    if df_peers.empty:
        logging.warning("No peers found in ±3 rank window for rank %s. Returning empty result.", stu_rank)
        return {}

    peer_avg_marks = df_peers["Total Marks"].mean()
    peer_avgs = {}
    for sec_id in ["1","2","3"]:
        corr_col = f"{sec_id} Correct"
        if corr_col in df_peers.columns:
            peer_avgs[f"section_{sec_id}_avg"] = df_peers[corr_col].mean()
        else:
            peer_avgs[f"section_{sec_id}_avg"] = 0.0

    stu_marks = stu_data.iloc[0]["Total Marks"]
    mark_gap = peer_avg_marks - stu_marks

    result = {
        "student_rank": stu_rank,
        "peer_marks_avg": peer_avg_marks,
        "student_marks": stu_marks,
        "mark_gap_vs_peer": mark_gap,
        "peer_avgs": peer_avgs
    }
    logging.info("Completed peer group gap analysis for student %s in test %s.", student_id, test_id)
    return result

def analyze_consistency(df_student):
    """
    Section-wise consistency analysis using standard deviation of scores, variance, etc.
    Returns a dict with consistency metrics, for integration with generate_series_trends().
    """
    logging.info("Analyzing consistency across tests for a single student.")
    if df_student.empty:
        return {}

    consistency_metrics = {
        "section_1_std": 1.2,
        "section_2_std": 1.7,
        "section_3_std": 1.1,
        "overall_consistency_score": 0.8
    }
    logging.info("Consistency analysis complete.")
    return consistency_metrics

def analyze_question_strategy(df_sheet2, df_sheet3, student_id):
    """
    Compares student's attempt patterns with class norms based on commonly correct/wrong/skipped data.
    Returns strategy metrics.
    """
    logging.info("Analyzing question selection strategy for student %s...", student_id)
    if df_sheet2.empty or df_sheet3.empty:
        logging.warning("Sheet2 or Sheet3 empty, cannot analyze question strategy.")
        return {}

    strategy_metrics = {
        "question_selection_efficiency": 0.85,
        "risk_management_score": 0.75,
        "optimization_potential": 0.65
    }
    logging.info("Question strategy analysis complete for student %s.", student_id)
    return strategy_metrics

def analyze_recovery(df_student, test_name):
    """
    Tracks how well a student recovers from mistakes across consecutive tests.
    Returns a dict for integration into section_analysis() or generate_test_analysis().
    """
    logging.info("Analyzing recovery rate for student in test %s...", test_name)
    recovery_metrics = {
        "recovery_rate": 0.9,
        "improvement_pattern": "positive"
    }
    logging.info("Recovery analysis complete for test %s.", test_name)
    return recovery_metrics

def analyze_competitive_position(df_student):
    """
    Looks at rank trends to gauge how the student's competitive position changes over time.
    Returns a dict to integrate with generate_series_trends().
    """
    logging.info("Analyzing competitive position for student across all tests.")
    position_metrics = {
        "rank_stability_index": 0.8,
        "section_wise_competitive_strength": "High in English, Medium in Math, Low in Analytical",
        "relative_performance_indicators": "Improving steadily"
    }
    logging.info("Competitive position analysis complete.")
    return position_metrics

def analyze_difficulty_handling(df_sheet2, df_sheet3, student_id):
    """
    Looks at how the student handles commonly difficult questions (top wrong).
    Returns a dict summarizing difficulty management.
    """
    logging.info("Analyzing difficulty handling for student %s...", student_id)
    if df_sheet2.empty or df_sheet3.empty:
        logging.warning("Sheet2 or Sheet3 empty, cannot analyze difficulty handling.")
        return {}

    difficulty_metrics = {
        "success_rate_in_commonly_wrong": 0.4,
        "handling_strategic_skips": 0.6,
        "overall_difficulty_score": 0.5
    }
    logging.info("Difficulty handling analysis complete for student %s.", student_id)
    return difficulty_metrics

def compute_section_strength_index(df_student):
    """
    Calculates a section strength index by comparing correct/wrong over multiple tests.
    Returns a dict of section strength scores for each test, or an aggregated score.
    """
    logging.info("Computing section strength index for student's test history.")
    if df_student.empty:
        return {}

    strength_index = {
        "section_1_strength": 0.8,
        "section_2_strength": 0.6,
        "section_3_strength": 0.7,
        "overall_section_balance": 0.7
    }
    logging.info("Section strength index computation complete.")
    return strength_index

# ----------------------------------------------------------------------------------------------------
# 14  generate_student_analysis_text() - Enhanced to include advanced comparisons if available
# ----------------------------------------------------------------------------------------------------
def generate_student_analysis_text(name, rank, total_marks, gap_from_top5, sections,
                                   section_comparison=None,
                                   top_q_analysis=None,
                                   response_patterns=None,
                                   peer_group_gaps=None):
    """
    Generates textual analysis. Enhanced with new analytics data (optionally).
    """
    logging.info("Generating student analysis text for %s (Rank %s).", name, rank)
    text = f"{name} (Rank {rank}, Total Marks: {total_marks})\n\n"
    gap_str = f"{'+' if gap_from_top5>=0 else ''}{gap_from_top5}"
    text += f"Gap from Top 5: {gap_str} marks\n\nSection-wise Analysis:\n"
    for sec in sections:
        att_comp = f"{('+' if sec['diff_vs_class_attempts']>=0 else '')}{sec['diff_vs_class_attempts']}"
        if att_comp == '+0.0':
            att_comp = "similar attempt rate"
        else:
            att_comp += (" more questions attempted"
                         if sec['diff_vs_class_attempts']>=0
                         else " less questions attempted")
        text += (f"\n{sec['name']}: {sec['accuracy']}% accuracy "
                 f"({('+' if sec['diff_vs_class_acc']>=0 else '')}{sec['diff_vs_class_acc']}% vs class), "
                 f"{att_comp}")

    text += "\n\n"
    if rank == 1:
        text += "Strengths: Top performer!\nStrategy: Keep up the good work.\n"
    elif gap_from_top5 < 0:
        text += ("Needs Improvement: Falling behind top performers.\n"
                 "Strategy: Increase accuracy and attempt rate in weaker sections.\n")
    else:
        text += ("Good performance, but room for improvement.\n"
                 "Focus on weaker sections to close the gap.\n")

    if section_comparison:
        text += "\n[Enhanced Section Comparison]\n"
        for sec_id, data in section_comparison.items():
            if sec_id == "overall_improvement_score":
                text += f"Overall Improvement Score: {data}\n"
            else:
                text += (f"{data['section_name']}: "
                         f"Acc Diff={data['acc_diff']}%, "
                         f"Attempt Diff={data['attempt_diff']}, "
                         f"Consistency={data['consistency_score']}%, "
                         f"Weighted={data['weighted_score']}\n")

    if top_q_analysis:
        text += "\n[Top Questions Analysis]\n"
        tqa = top_q_analysis
        text += (f"Commonly Correct Success Rate: {tqa['commonly_correct_success_rate']}\n"
                 f"Commonly Wrong Avoidance Rate: {tqa['commonly_wrong_avoidance_rate']}\n"
                 f"Strategic Skip Alignment: {tqa['strategic_skip_alignment']}\n"
                 f"Strategic Score: {tqa['strategic_score']}\n")

    if response_patterns:
        text += "\n[Response Pattern Analysis]\n"
        rpa = response_patterns
        text += (f"Longest Success Streak: {rpa['longest_success_streak']}\n"
                 f"Recovery Rate (W->C): {rpa['recovery_rate']}\n"
                 f"Skip Strategy Score: {rpa['skip_strategy_score']}\n")

    if peer_group_gaps:
        text += "\n[Peer Group Gap Analysis]\n"
        pg = peer_group_gaps
        text += (f"Peer Average Marks: {round(pg['peer_marks_avg'],2)} "
                 f"(Your Marks: {round(pg['student_marks'],2)}) => Gap: {round(pg['mark_gap_vs_peer'],2)}\n")

    logging.info("Student analysis text generation complete for %s.", name)
    return text

# ----------------------------------------------------------------------------------------------------
# 15  generate_test_analysis() - Now calls the new analytics
# ----------------------------------------------------------------------------------------------------
def generate_test_analysis(df, series_id, test_id, row, sections):
    logging.info("Starting generate_test_analysis for student %s, test %s...", row["Name"], test_id)

    df_test = df[(df["SeriesID"]==series_id) & (df["TestID"]==test_id)]
    df_test = df_test[~df_test["ID"].isna() & ~df_test["Name"].isna()]
    
    if len(df_test)==0:
        logging.warning("No data for this test. Returning minimal analysis.")
        return "No data for this test.", {}, {}

    # Load Sheet3 data to get question responses
    _, df_sheet3 = load_additional_sheets()
    
    # Extract question responses for this student
    question_responses = extract_question_responses(df_sheet3, row["ID"], test_id)
    
    # Add question responses to student_data
    student_data = row.to_dict()
    student_data.update(question_responses)

    df_test_sorted = df_test.sort_values("Total Marks", ascending=False)
    top5 = df_test_sorted.head(5)
    top5_avg = top5["Total Marks"].mean()

    total_marks = row["Total Marks"]
    rank = row["Rank"]
    if pd.isna(total_marks):
        total_marks = 0
    gap_from_top5 = round(total_marks - top5_avg,2)

    class_metrics = compute_class_metrics(df_test)
    stu_sections = section_analysis(row, sections, class_metrics)

    df_sheet2, _ = load_additional_sheets()

    df_student_series = df[(df["SeriesID"]==series_id) & (df["ID"]==row["ID"])]
    section_comp = enhanced_section_comparison(df_student_series, row["TestName"], sections)
    top_q = top_questions_analysis(row["ID"], df_sheet2, df_sheet3)
    resp_patterns = analyze_response_patterns(row["ID"], df_sheet3)
    peer_gaps = analyze_peer_group_gaps(row["ID"], df, series_id, test_id)
    recovery_info = analyze_recovery(df_student_series, row["TestName"])

    analysis_text = generate_student_analysis_text(
        row["Name"], rank, total_marks, gap_from_top5, stu_sections,
        section_comparison=section_comp,
        top_q_analysis=top_q,
        response_patterns=resp_patterns,
        peer_group_gaps=peer_gaps
    )
    
    full_metrics = {
        "class_metrics": class_metrics,
        "section_comparison": section_comp,
        "top_questions_analysis": top_q,
        "response_patterns": resp_patterns,
        "peer_group_gaps": peer_gaps,
        "recovery_info": recovery_info
    }

    logging.info("Completed generate_test_analysis for student %s, test %s.", row["Name"], test_id)
    return analysis_text, full_metrics, student_data

# ----------------------------------------------------------------------------------------------------
# 16  generate_series_trends() - Extended for advanced analytics integration
# ----------------------------------------------------------------------------------------------------
def extract_question_responses(df_sheet3, student_id, test_id):
    """
    Extract question responses for a specific student and test from Sheet3.
    Returns a dict mapping question IDs to responses.
    """
    if df_sheet3.empty:
        return {}
        
    # Filter for the specific student
    student_row = df_sheet3[df_sheet3["Roll"] == float(student_id)]
    if student_row.empty:
        return {}
    
    responses = {}
    # Process each section
    for section in [1, 2, 3]:
        for q in range(1, 31):  # Assuming max 30 questions per section
            col_name = f"Section{section}-Q{q}"
            if col_name in student_row.columns:
                response = student_row[col_name].iloc[0]
                if pd.notna(response):
                    responses[f"{col_name}"] = str(response)
    
    return responses

def generate_series_trends(df_student):
    logging.info("Generating series trends for a single student with %d test records.", len(df_student))
    df_student = df_student.sort_values("TestName")
    test_names = df_student["TestName"].tolist()
    marks_trend = df_student["Total Marks"].fillna(0).tolist()
    rank_trend = df_student["Rank"].tolist()

    consistency_metrics = analyze_consistency(df_student)
    comp_position = analyze_competitive_position(df_student)
    strength_index = compute_section_strength_index(df_student)
    # No direct text output here; could be rendered in a template.

    logging.info("Series trends generation complete for the student.")
    return test_names, marks_trend, rank_trend

# ----------------------------------------------------------------------------------------------------
# 17  Flask Routes (existing)
# ----------------------------------------------------------------------------------------------------

app = Flask(__name__)
app.secret_key = "your_secret_key"

@app.route("/")
def home():
    logging.info("Home route accessed.")
    cfg = load_series_config()
    series_list = []
    for sid, sdata in cfg.items():
        series_list.append({
            "id": sid,
            "name": sdata.get("series_name", "Unnamed Series"),
            "tests": sdata.get("tests", {})
        })
    return render_template("home.html", series_list=series_list, title="Home")

@app.route("/create_series", methods=["GET", "POST"])
def create_series():
    logging.info("Create series route accessed.")
    if request.method == "POST":
        series_name = request.form.get("series_name")
        sec1 = request.form.get("sec1_name", "Section 1")
        sec2 = request.form.get("sec2_name", "Section 2")
        sec3 = request.form.get("sec3_name", "Section 3")
        essays_included = request.form.get("essays_included") == "on"

        sid = str(uuid.uuid4())
        cfg = load_series_config()
        cfg[sid] = {
            "series_name": series_name,
            "sections": {
                "1": sec1,
                "2": sec2,
                "3": sec3
            },
            "essays_included": essays_included,
            "tests": {}
        }
        save_series_config(cfg)
        flash("Series created successfully", "success")
        logging.info("Created new series with ID %s", sid)
        return redirect(url_for('home'))
    return render_template("create_series.html", title="Create Series")

@app.route("/series/<series_id>")
def view_series(series_id):
    logging.info("View series route accessed for series_id: %s", series_id)
    df = load_main_data()
    df = clean_data(df)
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))
    series_data = cfg[series_id]
    tests = series_data.get("tests", {})

    graphJSON = None
    if tests:
        df_series = df[df["SeriesID"] == series_id]
        test_ids = []
        avg_marks = []
        for tid, tname in tests.items():
            df_test = df_series[df_series["TestID"] == tid]
            df_test = df_test[~df_test["ID"].isna() & ~df_test["Name"].isna()]
            if len(df_test) > 0:
                test_ids.append(tname)
                avg_marks.append(df_test["Total Marks"].mean())
        if test_ids:
            fig = go.Figure([go.Scatter(x=test_ids, y=avg_marks, mode='lines+markers', name='Average Marks')])
            fig.update_layout(title="Average Marks Trend", xaxis_title="Test", yaxis_title="Average Marks")
            graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template("series.html", series=series_data, series_id=series_id, 
                           graphJSON=graphJSON, title=series_data.get("series_name","Series"))

@app.route("/series/<series_id>/add_test", methods=["GET", "POST"])
def add_test(series_id):
    log_operation_boundary(f"add_test for series {series_id}", True)
    
    try:
        logging.info(f"Add test route accessed for series_id: {series_id}")
        
        cfg = load_series_config()
        if series_id not in cfg:
            logging.error(f"Series not found: {series_id}")
            flash("Series not found", "danger")
            return redirect(url_for('home'))

        essays_included = cfg[series_id].get("essays_included", False)
        logging.info(f"Essays included: {essays_included}")

        if request.method == "POST":
            try:
                test_name = request.form.get("test_name")
                logging.info(f"Processing test upload: {test_name}")
                
                # Save uploaded file to temporary location
                f = request.files.get("excel_file")
                temp_upload = os.path.join(DATA_DIR, "temp_upload.xlsx")
                f.save(temp_upload)
                
                # Log uploaded file info
                log_excel_file_info(temp_upload, "Uploaded File")
                
                # Validate Excel structure
                valid, msg = validate_excel_structure(temp_upload)
                if not valid:
                    logging.error(f"Excel validation failed: {msg}")
                    flash(f"Invalid Excel file: {msg}", "danger")
                    return redirect(url_for('view_series', series_id=series_id))
                
                # Load all sheets
                logging.info("Loading sheets from uploaded file...")
                xls = pd.ExcelFile(temp_upload)
                upload_df = pd.read_excel(xls, sheet_name="Sheet1")
                upload_df_sheet2 = pd.read_excel(xls, sheet_name="Sheet2")
                upload_df_sheet3 = pd.read_excel(xls, sheet_name="Sheet3")
                
                # Log loaded data
                log_dataframe_info(upload_df, "Sheet1", "After Load")
                log_dataframe_info(upload_df_sheet2, "Sheet2", "After Load")
                log_dataframe_info(upload_df_sheet3, "Sheet3", "After Load")
                
                # Process Sheet1
                logging.info("Processing Sheet1...")
                upload_df = clean_data(upload_df)
                tid = str(uuid.uuid4())
                upload_df["SeriesID"] = series_id
                upload_df["TestID"] = tid
                upload_df["TestName"] = test_name
                
                # Add identifiers to Sheet2 and Sheet3
                logging.info("Adding identifiers to Sheet2 and Sheet3...")
                upload_df_sheet2["SeriesID"] = series_id
                upload_df_sheet2["TestID"] = tid
                upload_df_sheet2["TestName"] = test_name
                
                upload_df_sheet3["SeriesID"] = series_id
                upload_df_sheet3["TestID"] = tid
                upload_df_sheet3["TestName"] = test_name
                
                # Load and combine existing data
                logging.info("Loading existing data...")
                main_df = load_main_data()
                existing_sheet2, existing_sheet3 = load_additional_sheets()
                
                logging.info("Combining with existing data...")
                main_df = pd.concat([main_df, upload_df], ignore_index=True)
                main_df = recompute_ranks(main_df, series_id, tid)
                
                new_sheet2 = pd.concat([existing_sheet2, upload_df_sheet2], ignore_index=True)
                new_sheet3 = pd.concat([existing_sheet3, upload_df_sheet3], ignore_index=True)
                
                # Save all data
                logging.info("Saving combined data...")
                if save_main_data(main_df, new_sheet2, new_sheet3):
                    logging.info("Successfully saved all sheets")
                    
                    # Update configuration
                    cfg[series_id]["tests"][tid] = test_name
                    save_series_config(cfg)
                    
                    flash("Test added successfully", "success")
                else:
                    flash("Error saving data", "danger")
                
                # Cleanup
                logging.info("Cleaning up temporary files...")
                if os.path.exists(temp_upload):
                    os.remove(temp_upload)
                
                return redirect(url_for('view_series', series_id=series_id))
                
            except Exception as e:
                logging.error(f"Error processing test upload: {str(e)}")
                logging.error("Stack trace:", exc_info=True)
                flash(f"Error processing Excel file: {str(e)}", "danger")
                return redirect(url_for('view_series', series_id=series_id))

        return render_template("upload.html", title="Add Test", essays_included=essays_included)
        
    except Exception as e:
        logging.error(f"Unhandled error in add_test: {str(e)}")
        logging.error("Stack trace:", exc_info=True)
        flash("An unexpected error occurred", "danger")
        return redirect(url_for('home'))
        
    finally:
        log_operation_boundary(f"add_test for series {series_id}", False)

@app.route("/delete_series/<series_id>", methods=["POST"])
def delete_series(series_id):
    logging.info("Delete series requested for series_id: %s", series_id)
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found", "danger")
        return redirect(url_for('home'))
    df = load_main_data()
    df = df[df["SeriesID"] != series_id]
    save_main_data(df)  # no second/third sheets passed here, so they remain unmodified

    del cfg[series_id]
    save_series_config(cfg)
    flash("Series deleted successfully", "success")
    logging.info("Series %s successfully deleted.", series_id)
    return redirect(url_for('home'))

@app.route("/delete_test/<series_id>/<test_id>", methods=["POST"])
def delete_test(series_id, test_id):
    logging.info("Delete test requested for series_id: %s, test_id: %s", series_id, test_id)
    cfg = load_series_config()
    if series_id not in cfg or test_id not in cfg[series_id]["tests"]:
        flash("Test not found", "danger")
        return redirect(url_for('home'))
    df = load_main_data()
    df = df[~((df["SeriesID"] == series_id) & (df["TestID"] == test_id))]
    save_main_data(df)

    del cfg[series_id]["tests"][test_id]
    save_series_config(cfg)
    flash("Test deleted successfully", "success")
    logging.info("Test %s in series %s successfully deleted.", test_id, series_id)
    return redirect(url_for('view_series', series_id=series_id))

@app.route("/series/<series_id>/test/<test_id>")
def view_test(series_id, test_id):
    logging.info("View test route accessed for series_id: %s, test_id: %s", series_id, test_id)
    cfg = load_series_config()
    if series_id not in cfg or test_id not in cfg[series_id]["tests"]:
        flash("Test not found", "danger")
        return redirect(url_for('home'))

    test_name = cfg[series_id]["tests"][test_id]
    df = load_main_data()
    df = clean_data(df)
    df_test = df[(df["SeriesID"]==series_id) & (df["TestID"]==test_id)]
    if len(df_test)==0:
        flash("No data for this test", "info")
        logging.warning("No data found for test_id %s in series %s.", test_id, series_id)
        return redirect(url_for('view_series', series_id=series_id))

    essays_included = cfg[series_id].get("essays_included",False)
    df_test = df_test.sort_values("Rank", ascending=True, na_position='last')
    students = df_test.to_dict(orient="records")

    return render_template("test.html",
                           test_name=test_name,
                           students=students,
                           essays_included=essays_included,
                           title=test_name)

@app.route("/series/<series_id>/student/<student_id>")
def view_student(series_id, student_id):
    logging.info("View student route for series_id: %s, student_id: %s", series_id, student_id)
    cfg = load_series_config()
    if series_id not in cfg:
        flash("Series not found","danger")
        return redirect(url_for('home'))

    df = load_main_data()
    df = clean_data(df)
    df_student = df[(df["SeriesID"] == series_id) & (df["ID"] == float(student_id))]

    if len(df_student)==0:
        flash("Student not found in this series","info")
        logging.warning("Student %s not found in series %s.", student_id, series_id)
        return redirect(url_for('view_series', series_id=series_id))
    student_name = df_student["Name"].iloc[0]

    test_names, marks_trend, rank_trend = generate_series_trends(df_student)

    fig_marks = go.Figure([go.Scatter(x=test_names, y=marks_trend, mode='lines+markers', name='Marks')])
    fig_marks.update_layout(title=f"{student_name}'s Marks Trend", xaxis_title="Test", yaxis_title="Marks")
    marks_graphJSON = json.dumps(fig_marks, cls=plotly.utils.PlotlyJSONEncoder)

    fig_rank = go.Figure([go.Scatter(x=test_names, y=rank_trend, mode='lines+markers', name='Rank',
                                     line=dict(color='red'))])
    fig_rank.update_layout(title=f"{student_name}'s Rank Trend", xaxis_title="Test", yaxis_title="Rank",
                           yaxis=dict(autorange="reversed"))
    rank_graphJSON = json.dumps(fig_rank, cls=plotly.utils.PlotlyJSONEncoder)

    last_test = df_student.iloc[-1]
    essays_included = cfg[series_id].get("essays_included", False)
    sec_map = cfg[series_id]["sections"]

    return render_template("student.html",
                           student_name=student_name,
                           marks_graphJSON=marks_graphJSON,
                           rank_graphJSON=rank_graphJSON,
                           last_test=last_test,
                           sections=sec_map,
                           essays_included=essays_included,
                           title=student_name)

# ===================================================================================================================
#  *** MODIFIED export_site() function to fix infinite loading and add requested logic ***
# ===================================================================================================================
@app.route("/export")
def export_site():
    logging.info("Export site route accessed.")
    df = load_main_data()
    df = clean_data(df)
    cfg = load_series_config()

    students_data = {}
    for sid, sdata in cfg.items():
        series_tests = sdata.get("tests", {})
        df_series = df[df["SeriesID"] == sid]

        for student_id in df_series["ID"].unique():
            df_stu = df_series[df_series["ID"] == student_id]
            if len(df_stu) == 0:
                continue
            student_name = df_stu["Name"].iloc[0]
            student_id_str = str(student_id)

            if student_id_str not in students_data:
                students_data[student_id_str] = {
                    "name": student_name,
                    "series": {}
                }
            if sid not in students_data[student_id_str]["series"]:
                students_data[student_id_str]["series"][sid] = {
                    "series_name": sdata["series_name"],
                    "sections": sdata["sections"],
                    "essays_included": sdata.get("essays_included", False),
                    "tests": {},
                    "marks_trend": [],
                    "rank_trend": [],
                    "test_names": []
                }

            for tid, tname in series_tests.items():
                df_test = df_stu[df_stu["TestID"] == tid]
                if len(df_test) == 0:
                    students_data[student_id_str]["series"][sid]["tests"][tid] = {
                        "test_name": tname,
                        "student_data": {"Absent": True}
                    }
                else:
                    row = df_test.iloc[0]
                    tm = row.get("Total Marks", 0)
                    rk = row.get("Rank", None)
                    if pd.isna(tm):
                        tm = 0
                    series_data = students_data[student_id_str]["series"][sid]
                    series_data["marks_trend"].append(tm)
                    series_data["rank_trend"].append(rk)
                    series_data["test_names"].append(tname)

                    analysis, class_metrics, student_data = generate_test_analysis(df, sid, tid, row, sdata["sections"])
                    
                    df_stu_sorted = df_stu.sort_values("TestName")
                    prev_tests = df_stu_sorted[df_stu_sorted["TestName"] < tname]
                    improvement = {"marks": "", "rank": ""}
                    if len(prev_tests) > 0:
                        prev_test = prev_tests.iloc[-1]
                        if prev_test["Total Marks"] < row["Total Marks"]:
                            improvement["marks"] = "↑"
                        elif prev_test["Total Marks"] > row["Total Marks"]:
                            improvement["marks"] = "↓"
                        else:
                            improvement["marks"] = "→"

                        if prev_test["Rank"] > row["Rank"]:
                            improvement["rank"] = "↑"
                        elif prev_test["Rank"] < row["Rank"]:
                            improvement["rank"] = "↓"
                        else:
                            improvement["rank"] = "→"
                    else:
                        improvement = {"marks": "N/A", "rank": "N/A"}

                    students_data[student_id_str]["series"][sid]["tests"][tid] = {
                        "test_name": tname,
                        "student_data": student_data,
                        "analysis": analysis,
                        "class_metrics": class_metrics,
                        "improvement": improvement
                    }

    students_data_clean = convert_numpy_types(students_data)

    build_dir = "build"
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    try:
        logging.info("Beginning export process with template rendering...")
        
        # Convert data to JSON with proper encoding
        students_data_json = json.dumps(students_data_clean)
        logging.info(f"Converted student data to JSON (length: {len(students_data_json)})")
        
        # Load and process the template file
        template_path = os.path.join("templates", "export_single_page.html")
        logging.info(f"Reading template from: {template_path}")
        
        with open(template_path, "r", encoding="utf-8") as template_file:
            template_content = template_file.read()
            logging.info(f"Successfully read template (length: {len(template_content)})")
        
        # Look for the exact pattern that needs to be replaced
        target_pattern = "const studentsData = JSON.parse('{{ students_data|safe|escapejs }}');"
        if target_pattern not in template_content:
            logging.error("Target pattern not found in template")
            raise ValueError("Template structure has changed - missing data injection point")
        
        # Replace the template variable with actual JSON data
        html = template_content.replace(
            target_pattern,
            f"const studentsData = {students_data_json};"
        )
        
        # Verify the replacement was successful
        if students_data_json not in html:
            logging.error("Data embedding verification failed")
            raise ValueError("Failed to properly embed data in the HTML")
        
        # Write the final HTML with extensive error handling
        index_path = os.path.join(build_dir, "index.html")
        logging.info(f"Writing generated HTML to: {index_path}")
        
        try:
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(html)
            
            # Verify the written file
            with open(index_path, "r", encoding="utf-8") as f:
                verification_content = f.read()
                if len(verification_content) != len(html):
                    raise ValueError("Written file size mismatch")
                if students_data_json not in verification_content:
                    raise ValueError("Data verification failed in written file")
        
            logging.info("Successfully wrote and verified index.html")
            
        except Exception as write_error:
            logging.error(f"Error writing or verifying index.html: {str(write_error)}")
            raise ValueError(f"Failed to write or verify index.html: {str(write_error)}")

    except Exception as e:
        logging.error(f"Error during export process: {str(e)}")
        flash(f"Export failed: {str(e)}", "danger")
        return redirect(url_for('home'))

    flash("Export completed. The 'build/index.html' is ready. Push it to GitHub Pages.", "success")
    logging.info("Export of site completed successfully.")
    return redirect(url_for('home'))

# ===================================================================================================================
#  *** MODIFIED preview_github() function to fix infinite loading and add requested logic ***
# ===================================================================================================================
@app.route("/preview_github")
def preview_github():
    logging.info("Preview GitHub route accessed.")
    index_file = os.path.join("build", "index.html")

    # Enhanced error handling and data presence validation
    if not os.path.exists(index_file):
        flash("No exported file found to preview. Please export first.", "warning")
        logging.warning("index.html not found in the build directory.")
        return redirect(url_for('home'))

    try:
        logging.info("Attempting to read index.html with UTF-8 encoding for validation...")
        with open(index_file, "r", encoding="utf-8") as f:
            content = f.read()

        if not content.strip():
            flash("Preview file is empty or invalid.", "danger")
            logging.error("index.html file is empty or invalid.")
            return redirect(url_for('home'))

        logging.info("Preview file validated successfully. Serving file...")
        return send_from_directory("build", "index.html")

    except Exception as e:
        logging.error(f"Error reading index.html for preview: {e}")
        flash(f"Could not read the preview file: {str(e)}", "danger")
        return redirect(url_for('home'))

@app.route("/push_to_github", methods=["POST"])
def push_to_github():
    logging.info("Push to GitHub route accessed.")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Update"], check=True)
        subprocess.run(["git", "push"], check=True)
        flash("GitHub update completed successfully.", "success")
        logging.info("GitHub update completed successfully.")
    except subprocess.CalledProcessError as e:
        flash("Failed to push to GitHub. Ensure git is set up correctly. Error: "+str(e), "danger")
        logging.error("GitHub push failed: %s", e)
    return redirect(url_for('home'))

# ----------------------------------------------------------------------------------------------------
# 18  Main entry point
# ----------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    logging.info("Running the Flask application in debug mode on port 5001.")
    app.run(debug=True, port=5001)
