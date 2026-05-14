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

    results_list.controls.append(ft.Divider())
    results_list.controls.append(ft.Text("SPACING VIOLATIONS:", weight="bold", size=18))

    if conflicts:
        for c in conflicts:
            results_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.WARNING_AMBER, color="orange"),
                            ft.Text(f"BOUNDARY OVERLAP", weight="bold")
                        ]),
                        ft.Text(f"'{c['equipment_a'].replace('PLAN ', '').strip()}' ({c['boundary_used_a'].lower()}) TOO CLOSE TO '{c['equipment_b'].replace('PLAN ', '').strip()}' ({c['boundary_used_b'].lower()})", size=12),
                    ]),
                    bgcolor=ft.Colors.RED_500,
                    padding=10,
                    border_radius=5,
                )
            )
    else:
        results_list.controls.append(
            ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK_CIRCLE, color="green", size=30),
                    ft.Text("No spacing violations found", size=16, weight="bold", color="green")
                ]),
                bgcolor=ft.Colors.GREEN_100,
                padding=15,
                border_radius=5
            )
        )

    results_list.controls.append(ft.Divider())
    results_list.controls.append(ft.Text("DISCREPANCY REPORT:", weight="bold", size=18))

    if drawing_details and quote_basket:
        #initialise mappings of quote items to drawing items using fuzzy matching
        quote_to_drawing_map = {}
        unmatched_quote_items = []
        
        #look at each item in the quote
        for quote_item in quote_basket.keys():
            #find closest match in drawing (if there is one)
            matched_drawing_item, score = find_best_match(quote_item, list(drawing_details.keys()))
            
            #was one found
            if matched_drawing_item:
                #add to map
                quote_to_drawing_map[quote_item] = {
                    'drawing_item': matched_drawing_item, #what was the match
                    'score': score #how strong was the match 
                }
            else:
                unmatched_quote_items.append(quote_item) #wasn't matched list (maybe missing)
        
        print(quote_to_drawing_map)
        #which drawing items got added to the quote match list
        matched_drawing_items = set(item['drawing_item'] for item in quote_to_drawing_map.values())
        #looking at all the drawing items, which ones weren't matched with a quote one
        unmatched_drawing_items = [item for item in drawing_details.keys() if item not in matched_drawing_items and drawing_details[item]['Quantity'] > 0]
        
        #initialise to no discrepancies found yet
        mismatches_found = False
        
        #check for quantity mismatches in matched items
        for quote_item, match_info in quote_to_drawing_map.items():
            drawing_item = match_info['drawing_item']
            match_score = match_info['score']
            
            quote_qty = quote_basket[quote_item]
            draw_qty = drawing_details[drawing_item]['Quantity']
            
            #are the quantities different
            if draw_qty != quote_qty:
                #at least one discrepancy found
                mismatches_found = True
                #discrepancy needs displaying
                #the match score is added if human intervention needed
                results_list.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.WARNING_AMBER, color="orange"),
                                ft.Text(f"QUANTITY MISMATCH (Match: {match_score:.1f}%)", weight="bold")
                            ]),
                            ft.Text(f"Drawing: '{drawing_item}' = {draw_qty}", size=12),
                            ft.Text(f"Quote:   '{quote_item}' = {quote_qty}", size=12),
                        ]),
                        bgcolor=ft.Colors.RED,
                        padding=10,
                        border_radius=5,
                    )
                )
        
        #report items in quote but not in drawing
        for quote_item in unmatched_quote_items:
            mismatches_found = True
            quote_qty = quote_basket[quote_item]
            if "Gate" not in quote_item:
                results_list.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.ERROR_OUTLINE, color="red"),
                                ft.Text("MISSING FROM DRAWING", weight="bold")
                            ]),
                            ft.Text(f"Quote: '{quote_item}' = {quote_qty}", size=12),
                            ft.Text("No matching item found in drawing", size=11, italic=True),
                        ]),
                        bgcolor=ft.Colors.ORANGE,
                        padding=10,
                        border_radius=5,
                    )
                )
        
        #report items in drawing but not in quote
        for drawing_item in unmatched_drawing_items:
            mismatches_found = True
            draw_qty = drawing_details[drawing_item]['Quantity']
            if "Gate" not in drawing_item:
                results_list.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.ERROR_OUTLINE, color="red"),
                                ft.Text("MISSING FROM QUOTE", weight="bold")
                            ]),
                            ft.Text(f"Drawing: '{drawing_item}' = {draw_qty}", size=12),
                            ft.Text("No matching item found in quote", size=11, italic=True),
                        ]),
                        bgcolor=ft.Colors.ORANGE,
                        padding=10,
                        border_radius=5,
                    )
                )
        
        #success message if everything matches
        if not mismatches_found:
            results_list.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CHECK_CIRCLE, color="green", size=30),
                        ft.Text("All quantities match", size=16, weight="bold", color="green")
                    ]),
                    bgcolor=ft.Colors.GREEN_100,
                    padding=15,
                    border_radius=5
                )
            )

    page.update()

if __name__ == "__main__":
    ft.run(main)