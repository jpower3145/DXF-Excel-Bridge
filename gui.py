import sys
import flet as ft
import asyncio
import subprocess
import ezdxf

# Import from our custom modules
from geometry_logic import extract_drawing_items, check_distances
from data_parser import extract_quote_data, find_best_match

async def main(page: ft.Page) -> None:
    page.title = "DXF vs Quote Validator"
    page.scroll = "adaptive"
    page.window_width = 600
    page.window_height = 300
    
    #file_uploader.py needs to be run before this
    if len(sys.argv) < 3:
        try:
            subprocess.run([
                sys.executable,     
                "file_uploader.py",  
            ], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running extraction: {e}")
            return
    
    #set the path names from file_uploader
    dxf_path = sys.argv[1]
    quote_path = sys.argv[2]

    #set dxf loading wheel
    dxf_spinner = ft.ProgressRing(width=20, height=20, visible=False)
    dxf_icon = ft.Icon(ft.Icons.CIRCLE_OUTLINED, visible=True)
    dxf_text = ft.Text("Waiting to scan Drawing...", size=16)
    
    #set excel loading wheel
    quote_spinner = ft.ProgressRing(width=20, height=20, visible=False)
    quote_icon = ft.Icon(ft.Icons.CIRCLE_OUTLINED, visible=True)
    quote_text = ft.Text("Waiting to scan Quote...", size=16)
    
    results_list = ft.Column()
    
    #add the elements
    page.add(
        ft.Container(
            content=ft.Column([
                ft.Text("Drawing-Quote Discrepancy Checker", size=24, weight="bold"),
                ft.Divider(),
                ft.Row([dxf_spinner, dxf_icon, dxf_text]),
                ft.Row([quote_spinner, quote_icon, quote_text]),
                results_list
            ]),
            padding=20
        )
    )
    
    #render the initial page
    page.update()
    #give some time to render
    #this is asynchronous because it should be a spawned subprocess
    await asyncio.sleep(0.5)

    #loop to perform computation
    loop = asyncio.get_running_loop()

    #show the dxf is being worked on in UI
    dxf_icon.visible = False
    dxf_spinner.visible = True
    dxf_text.value = f"Reading Drawing Items..."
    page.update()

    try:
        #in a separate thread, load the dxf file
        dxf_file = await loop.run_in_executor(None, ezdxf.readfile, dxf_path)
        #parse the dxf file to find all the unique items 
        drawing_details, bounds = await loop.run_in_executor(None, extract_drawing_items, dxf_file)
        conflicts = await loop.run_in_executor(None, check_distances, bounds)
        #remove loading status in UI
        dxf_spinner.visible = False
        #update to show completion
        dxf_icon.name = ft.Icons.CHECK_CIRCLE
        dxf_icon.color = "green"
        dxf_icon.visible = True
        dxf_text.value = "Drawing Data Extracted"
        page.update()
    except Exception as e:
        dxf_spinner.visible = False
        dxf_icon.name = ft.Icons.CANCEL
        dxf_icon.color = "red"
        dxf_icon.visible = True
        dxf_text.value = f"Error Parsing Drawing: {str(e)}"
        page.update()
        return

    #show quote is not being worked on (runs alot faster then dxf)
    quote_icon.visible = False
    quote_spinner.visible = True
    quote_text.value = "Reading Excel Quote..."
    page.update()

    try:
        #again in seperate thread, parse the quote data from the excel
        quote_basket = await loop.run_in_executor(None, extract_quote_data, quote_path)

        #loading wheel done
        quote_spinner.visible = False
        #update to show completion
        quote_icon.name = ft.Icons.CHECK_CIRCLE
        quote_icon.color = "green"
        quote_icon.visible = True
        quote_text.value = "Quote Data Extracted"
        page.update()
    except Exception as e:
        quote_spinner.visible = False
        quote_icon.name = ft.Icons.CANCEL
        quote_icon.color = "red"
        quote_icon.visible = True
        quote_text.value = f"Error: {str(e)} ENSURE ALL EXCEL FILES ARE CLOSED"
        page.update()
        return


    page.update()

if __name__ == "__main__":
    ft.run(main)