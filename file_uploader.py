import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

#States and Constants
dwg_set = False
excel_set = False
dxf_path = ""
excel_path = ""

def convert_file(dwg_path_str):
    executable = "ODAFileConverter.exe"
    dwg_file = Path(dwg_path_str)
    output_folder = Path.cwd() / "Converted_DXFs"
    output_folder.mkdir(exist_ok=True)
    
    if not Path(executable).exists():
        messagebox.showerror("Error", "ODAFileConverter.exe not found!")
        return False # Return False so we don't update the UI

    try:
        with tempfile.TemporaryDirectory() as base_temp:
            temp_path = Path(base_temp)
            in_dir, out_dir = temp_path / "in", temp_path / "out"
            in_dir.mkdir(); out_dir.mkdir()

            shutil.copy2(dwg_file, in_dir / dwg_file.name)

            subprocess.run([
                executable, str(in_dir), str(out_dir), 
                "ACAD2018", "DXF", "0", "1"
            ], check=True, capture_output=True)

            dxf_name = dwg_file.with_suffix(".dxf").name
            global dxf_path
            dxf_path = output_folder / dxf_name
            
            if (out_dir / dxf_name).exists():
                shutil.move(str(out_dir / dxf_name), str(dxf_path))
                return True # Success
            else:
                raise FileNotFoundError("Conversion failed.")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to convert: {str(e)}")
        return False

def run_extraction_script(dxf_p, excel_p):
    try:
        # Note: Added str() to paths to ensure they are CLI-friendly
        subprocess.run([sys.executable, "gui.py", str(dxf_p), str(excel_p)], check=True)
    except Exception as e:
        print(f"Error running extraction: {e}")

def check_ready():
    if dwg_set and excel_set:
        # Give a tiny delay so the user can actually see the button change before it closes
        root.after(500, lambda: [root.destroy(), run_extraction_script(dxf_path, excel_path)])

def on_dxf_click():
    file_path = filedialog.askopenfilename(
        title="Select DWG",
        filetypes=[("AutoCAD Drawing", "*.dwg")]
    )
    
    if file_path:
        success = convert_file(file_path)
        if success:
            global dwg_set
            dwg_set = True
            # Update the button text to the filename
            btn_dxf.config(text=f"Uploaded: {Path(file_path).name}", fg="green")
            check_ready()

def on_excel_click():
    global excel_path, excel_set
    path = filedialog.askopenfilename(
        title="Select Quote Excel File",
        filetypes=[("Excel files", "*.xlsx *.xls")]
    )
    
    if path:
        excel_path = path
        excel_set = True
        # Update the button text to the filename
        btn_excel.config(text=f"Uploaded: {Path(path).name}", fg="green")
        check_ready()

#SETUP
root = tk.Tk()
root.title("Simple DWG Converter")
root.geometry("500x250")

tk.Label(root, text="DWG to DXF Converter", font=("Arial", 12, "bold"), pady=10).pack()

# Excel Button
btn_excel = tk.Button(root, text="Choose Excel Quote", command=on_excel_click, 
                      width=40, height=2, bg="#f0f0f0")
btn_excel.pack(pady=10)

# DWG Button
btn_dxf = tk.Button(root, text="Choose DWG Drawing", command=on_dxf_click, 
                    width=40, height=2, bg="#f0f0f0")
btn_dxf.pack(pady=10)

root.mainloop()