import pandas as pd
from fuzzywuzzy import fuzz
import re
from typing import Dict, List, Tuple, Optional, Any

FUZZY_ACCEPTANCE_LEVEL = 50  # percent

def extract_quote_data(quote_path: str) -> Dict[str, float]:
    """Reads the Sage Input sheet of the Quote Excel file and extracts items."""
    try:
        quote_data = pd.read_excel(quote_path, sheet_name='Sage Input')
    except (FileNotFoundError, ValueError) as e:
        raise RuntimeError(f"Failed to load Excel data: {e}")

    # "Equipment" and "Surfacing" are values in the Description column (iloc[:,4])
    start_idx = quote_data[quote_data.iloc[:, 4] == "Equipment"].index[0]
    end_idx   = quote_data[quote_data.iloc[:, 4] == "Surfacing"].index[0]

    # Slice between the two markers (+1 to skip the "Equipment" row itself)
    equipment_data = quote_data.iloc[start_idx + 1 : end_idx].copy()

    # Pull Item code (col 0) and Description (col 4) to build Item Name,
    # plus Quantity (col 6)
    equipment_data = equipment_data.iloc[:, [0, 4, 6]].copy()
    equipment_data.columns = ['Item Code', 'Description', 'Quantity']

    #Match the format in the plans
    equipment_data['Code'] = (
        equipment_data['Item Code']
        .astype(str)
        .str.replace('/','-')
        .str.strip()
    )

    # Merge Description and Code into a single Item Name: "Description (CODE)"
    equipment_data['Item Name'] = (
        equipment_data['Description'].astype(str)
        + ' '
        + equipment_data['Code']
    )

    # Coerce Quantity to numeric; default missing to 0
    equipment_data['Quantity'] = (
        pd.to_numeric(equipment_data['Quantity'], errors='coerce').fillna(0)
    )

    # Drop rows where Description is empty, NaN, or the placeholder "0"
    equipment_data = equipment_data[
        (equipment_data['Description'].astype(str) != '0') &
        (equipment_data['Description'].notna())
    ]

    # Final output: just the two required columns
    result = equipment_data[['Item Name', 'Quantity']].reset_index(drop=True)

    print(result)

    return result.groupby('Item Name')['Quantity'].sum().to_dict()

def normalise_name(name: str) -> str:
    """Cleans up item strings to improve fuzzy matching accuracy."""
    # Remove 'PLAN ' prefix if present
    name = re.sub(r'-', '', name, flags=re.IGNORECASE)
    name = re.sub(r'^PLAN\s+', '', name, flags=re.IGNORECASE)
    
    #lower case for consistency
    name = name.lower()
    
    #removals that make matches more accurate
    patterns_to_remove = [
        r'\s*-\s*[stg]gf\*?',       # Remove - SGF*, - TGF*, - GGF*
        r'\s[()]',                 # Remove brackets
        r'\s*including.*',          # Remove "including ..."
        r'\s*approx\..*',           # Remove "approx. ..."
        r'\s+\d+\s*x\s*\d+mm',      # Remove dimensions like "1 X 600mm"
        #Cleans up the fact a swing set can have > 1 item in the quote
        r'\s*frame only|\s*with shackles|\s*seat & chains for team swing frame', 
        r'\s*timber\s*',            # Remove "timber"
    ]
    
    normalised = name
    for pattern in patterns_to_remove:
        normalised = re.sub(pattern, '', normalised, flags=re.IGNORECASE)
    
    #remove extra whitespace
    normalised = ' '.join(normalised.split())
    return normalised.strip()

def find_best_match(item_name: str, item_list: List[str]) -> Tuple[Optional[str], float]:
    """Compares an item against a list using fuzzy string matching."""
    #normalise the quote entry
    normalised_target = normalise_name(item_name)
    
    best_score = 0
    best_match = None

    #cycle each item in drawing
    for candidate in item_list:
        #normalise this drawing item
        normalised_candidate = normalise_name(candidate)
        #direct char by char comparisons (quite rigid 'log' vs 'log')
        #ratio = fuzz.ratio(normalised_target, normalised_candidate)
        #looks for smaller matches within a longer comparator ('log' vs 'logs')
        partial_ratio = fuzz.partial_ratio(normalised_target, normalised_candidate)
        #splits up strings ignoring different orders (flexible 'timber log' vs 'log timber')
        token_sort_ratio = fuzz.token_sort_ratio(normalised_target, normalised_candidate)
        
        #prioritise the flexible sort ratio slightly more
        score = (partial_ratio * 0.3 + token_sort_ratio * 0.7)
        
        #is this current drawing item the closest to the queried quote item
        if score > best_score:
            best_score = score
            best_match = candidate
    
    #after checking all, is our best match good enough (>50%)
    if best_score >= FUZZY_ACCEPTANCE_LEVEL:
        return best_match, best_score
    else:
        return None, best_score