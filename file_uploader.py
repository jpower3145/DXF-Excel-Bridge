import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path


def convert_file(dwg_path):
    executable = "ODAFileConverter.exe"
    dwg_file = Path(dwg_path)

    output_folder = Path.cwd() / "Converted_DXFs"
    output_folder.mkdir(exist_ok=True)
    if not Path(executable).exists():
        messagebox.showerror("Error", "ODAFileConverter.exe not found!")
        return

    try:
        with tempfile.TemporaryDirectory() as base_temp:
            temp_path = Path(base_temp)
            in_dir, out_dir = temp_path / "in", temp_path / "out"
            in_dir.mkdir(); out_dir.mkdir()

            #copy file to temp sandbox
            shutil.copy2(dwg_file, in_dir / dwg_file.name)

            #run ODA
            subprocess.run([
                executable, str(in_dir), str(out_dir), 
                "ACAD2018", "DXF", "0", "1"
            ], check=True, capture_output=True)

            # Move result back to original folder
            dxf_name = dwg_file.with_suffix(".dxf").name
            global dxf_path
            dxf_path = output_folder / dxf_name
            
            if (out_dir / dxf_name).exists():
                shutil.move(str(out_dir / dxf_name), str(dxf_path))
                messagebox.showinfo("Success", "DXF Uploaded")
            else:
                raise FileNotFoundError("Conversion failed - no DXF produced.")
            

    except Exception as e:
        messagebox.showerror("Error", f"Failed to convert: {str(e)}")

def run_extraction_script(dxf_path, excel_path):
    # This is like typing 'python extraction.py path1 path2' in your terminal
    try:
        subprocess.run([
            sys.executable,        # The path to your current python interpreter
            "dxf_extraction.py",   # The script you want to run
            dxf_path,              # Argument 1
            excel_path             # Argument 2
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running extraction: {e}")

def check_ready():
    if dwg_set and excel_set:
        root.destroy()
        run_extraction_script(dxf_path, excel_path)

def on_dxf_click():
    file_path = filedialog.askopenfilename(
        title="Select DWG",
        filetypes=[("AutoCAD Drawing", "*.dwg")]
    )
    
    if file_path:
        convert_file(file_path)
        global dwg_set
        dwg_set = True
        check_ready()

def on_excel_click():
    global excel_path
    excel_path = filedialog.askopenfilename(
        title="Select Quote Excel File",
        filetypes=[("Excel files", "*.xlsx *.xls")]
    )
    
    if excel_path:
        global excel_set
        excel_set = True
        messagebox.showinfo("Success", "Excel File Uploaded")
        check_ready()
        



#SETUP
global dwg_set
dwg_set = False
global excel_set
excel_set = False

root = tk.Tk()
root.title("Simple DWG Converter")
root.geometry("500x200")

label = tk.Label(root, text="DWG to DXF Converter", pady=10)
label.pack()

btn_excel = tk.Button(root, text="Choose Excel Quote", command=on_excel_click, width=20, height=2)
btn_excel.pack(pady=10)

btn_dxf = tk.Button(root, text="Choose DWG Drawing", command=on_dxf_click, width=20, height=2)
btn_dxf.pack(pady=10)

root.mainloop()
