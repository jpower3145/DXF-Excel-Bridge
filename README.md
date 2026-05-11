# DXF-to-Quote Validator
### Automated Spatial Analysis & Quote-Design Anomaly Checker for Playground Engineering

## Overview
This professional-grade tool automates the reconciliation between **AutoCAD Site Drawings (DWG/DXF)** and **Commercial Quotes (Excel)**. Developed as a solution for the playground equipment industry, it ensures that every item quoted is present on the plan and verified for safety compliance according to **EN1176 standards**.

The project in Python blends spatial mathematics, and GUI development.

## Key Features
* **Geometric Extraction & Transformation:** Parses complex CAD entities (LWPolylines, Arcs, Splines) and translates local block coordinates into global world-space coordinates.
* **Fuzzy String Matching:** Employs the Levenshtein distance algorithm to reconcile inconsistent naming conventions between technical CAD blocks and commercial Sage-input records.
* **Automated Safety Auditing:** Detects "Too Close" and "Overlap" violations between equipment impact areas using `Shapely` polygon intersections [cite: dxf_extraction.py].
* **Asynchronous Multi-Threading:** Features a Flet-based UI that remains responsive during heavy computational tasks by utilizing Python's `asyncio` and `run_in_executor`.
* **Automated CAD Conversion:** Integrates with the ODA File Converter to provide a seamless workflow from raw proprietary `.dwg` files to processed data.

## Project Structure
* `gui.py`: The application frontend using Flet UI.
* `geometry_logic.py`: The "brain" of the project; handles all spatial math, DXF parsing, and polygon logic.
* `data_parser.py`: Manages Excel data extraction and string similarity algorithms.
* `file_uploader.py`: A Tkinter-based entry point for secure file selection and CAD conversion.

## Tech Stack
* **Language:** Python 3.12+
* **Spatial Math:** `Shapely`, `NumPy`
* **CAD Interface:** `ezdxf`
* **Data Analysis:** `Pandas`, `Openpyxl`
* **String Matching:** `FuzzyWuzzy`
* **UI Frameworks:** `Flet` (Flutter-based Python), `Tkinter`

## Setup & Installation
### 1. Prerequisites
This tool relies on the **ODA File Converter** for initial CAD processing. 
* Download and install the latest version from the [Official ODA Website](https://www.opendesign.com/guestfiles/oda_file_converter).

### 2. Dependencies
Install the required Python libraries:
```bash
pip install flet ezdxf pandas shapely fuzzywuzzy openpyxl numpy
```

### 3. Usage
1. Run `python file_uploader.py`.
2. Select your Excel Quote and DWG Site Plan.
3. The tool will convert the drawing and automatically launch the Discrepancy Checker.

## Portfolio Context
This project was developed by **Joe Power**, a Computer Science graduate from **Lancaster University**. It showcases the ability to translate complex industrial requirements (EN1176 safety standards) into robust, maintainable, and user-friendly software solutions.
