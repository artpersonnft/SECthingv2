import importlib
import subprocess
import sys
from pathlib import Path

# List of required packages
required_packages = {
    'pandas': 'pandas',
    'matplotlib': 'matplotlib',
    'mplcursors': 'mplcursors',
    'logging': 'logging',  # Built-in, no install needed
    'os': 'os',  # Built-in, no install needed
    'gc': 'gc',  # Built-in, no install needed
    'collections': 'collections'  # Built-in, no install needed
}

# Function to install package if missing
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# Check and install dependencies
for pkg_name, pip_name in required_packages.items():
    try:
        importlib.import_module(pkg_name)
    except ImportError:
        print(f"Installing {pkg_name}...")
        install_package(pip_name)
        print(f"{pkg_name} installed successfully.")

# Now import the packages after installation
import pandas as pd
import os
import matplotlib.pyplot as plt
import mplcursors
from collections import defaultdict
import logging
import gc

# Get the current working directory
cwd = os.getcwd()

# List all subdirectories in the CWD
subdirs = [d for d in os.listdir(cwd) if os.path.isdir(os.path.join(cwd, d))]

if not subdirs:
    print("No subdirectories found in the current directory.")
    exit(1)

# Print numbered list of subdirectories
print("Available subdirectories:")
for i, subdir in enumerate(subdirs, 1):
    print(f"{i}. {subdir}")

# Get user selection for subdirectory
subdir_selection = int(input("Select a subdirectory by number: "))
if subdir_selection < 1 or subdir_selection > len(subdirs):
    print("Invalid subdirectory selection.")
    exit(1)

# Get the selected subdirectory path
selected_subdir = subdirs[subdir_selection - 1]
subdir_path = os.path.join(cwd, selected_subdir)

# List all CSV files in the selected subdirectory
csv_files = [f for f in os.listdir(subdir_path) if f.endswith('.csv')]

if not csv_files:
    print(f"No CSV files found in the subdirectory '{selected_subdir}'.")
    exit(1)

# Print numbered list of CSV files
print(f"\nAvailable CSV files in '{selected_subdir}':")
for i, file in enumerate(csv_files, 1):
    print(f"{i}. {file}")

# Get user selection for CSV file
csv_selection = int(input("Select a CSV file by number: "))
if csv_selection < 1 or csv_selection > len(csv_files):
    print("Invalid CSV file selection.")
    exit(1)

# Load the selected CSV with low_memory=False to handle mixed types
csv_file = os.path.join(subdir_path, csv_files[csv_selection - 1])
print(f"Loading: {csv_file}")
df = pd.read_csv(csv_file, low_memory=False)

# Set up logging
log_file = os.path.join(cwd, 'swap_analysis.log')
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Ensure 'Dissemination Identifier' and 'Original Dissemination Identifier' are treated as strings
df['Dissemination Identifier'] = df['Dissemination Identifier'].astype(str)
df['Original Dissemination Identifier'] = df['Original Dissemination Identifier'].astype(str).replace('nan', '')

# Function to trace the chain to its root
def find_root_chain(df, dissem_id, visited=None):
    if visited is None:
        visited = set()
    chain = [dissem_id]
    visited.add(dissem_id)
    
    row = df[df['Dissemination Identifier'] == dissem_id]
    if row.empty:
        return chain
    
    orig_id = row['Original Dissemination Identifier'].iloc[0]
    if orig_id and orig_id != '' and orig_id not in visited:
        chain.extend(find_root_chain(df, orig_id, visited))
    
    return chain

# Build chains for all unique dissemination IDs
unique_dissem_ids = df['Dissemination Identifier'].unique()
chains = {}
for dissem_id in unique_dissem_ids:
    chain = find_root_chain(df, dissem_id)
    root_id = chain[-1] if len(chain) > 1 else dissem_id
    if root_id not in chains:
        chains[root_id] = []
    chains[root_id].append(dissem_id)

# Function to aggregate notional and quantity by currency for a chain
def aggregate_chain_notional(chain_df):
    non_basket_df = chain_df[chain_df['Product name'] != 'Equity:Swap:PriceReturnBasicPerformance:Basket'].copy()
    if non_basket_df.empty:
        return {'notional': {}, 'quantity': {}}
    
    non_basket_df.loc[:, 'Notional amount-Leg 1'] = pd.to_numeric(non_basket_df.iloc[:, 19], errors='coerce').fillna(0)
    non_basket_df.loc[:, 'Total notional quantity-Leg 1'] = pd.to_numeric(non_basket_df.iloc[:, 25], errors='coerce').fillna(0)
    currency_series = non_basket_df.iloc[:, 21].fillna('').astype(str).str.strip().str.upper()
    
    notional_totals = defaultdict(float)
    quantity_totals = defaultdict(float)
    for _, row in non_basket_df.iterrows():
        currency = row['Notional currency-Leg 1'] if row['Notional currency-Leg 1'] else 'UNK'
        notional_totals[currency] += row['Notional amount-Leg 1']
        quantity_totals[currency] += row['Total notional quantity-Leg 1']
    
    return {'notional': dict(notional_totals), 'quantity': dict(quantity_totals)}

# Identify chains not terminated (no TERM or ETRM in the chain's final event) and starting with NEWT
open_chains = []
for root_id, chain_ids in chains.items():
    chain_df = df[df['Dissemination Identifier'].isin(chain_ids)].copy()
    chain_df.loc[:, 'Event timestamp'] = pd.to_datetime(chain_df['Event timestamp'], format='%Y-%m-%dT%H:%M:%SZ')
    
    root_event = chain_df[chain_df['Dissemination Identifier'] == root_id]
    if root_event.empty or root_event['Action type'].iloc[0] != 'NEWT':
        continue
    
    latest_event = chain_df.loc[chain_df['Event timestamp'].idxmax()]
    if latest_event['Action type'] != 'TERM' or latest_event['Event type'] != 'ETRM':
        # Aggregate notional and quantity for the chain
        chain_notional = aggregate_chain_notional(chain_df)
        open_chains.append({
            'Root ID': root_id,
            'Last Dissemination ID': latest_event['Dissemination Identifier'],
            'Last Action': latest_event['Action type'],
            'Event Timestamp': latest_event['Event timestamp'],
            'Execution Timestamp': latest_event['Execution Timestamp'],
            'Expiration Date': latest_event['Expiration Date'],
            'Swap Type': latest_event['Product name'],
            **{f'Notional_{k}': v for k, v in chain_notional['notional'].items()},
            **{f'Quantity_{k}': v for k, v in chain_notional['quantity'].items()}
        })

# Print open chains
print(f"\nTotal unique position chains: {len(chains)}")
print(f"Open (non-TERM'd or non-ETRM) chains starting with NEWT: {len(open_chains)}")
print("\nDetails of open chains (not terminated by TERM or ETRM):")
for chain in open_chains:
    print(f"Root ID: {chain['Root ID']}")
    print(f"Last Dissemination ID: {chain['Last Dissemination ID']}")
    print(f"Last Action: {chain['Last Action']}")
    print(f"Event Timestamp: {chain['Event Timestamp']}")
    print(f"Execution Timestamp: {chain['Execution Timestamp']}")
    print(f"Expiration Date: {chain['Expiration Date']}")
    print(f"Swap Type: {chain['Swap Type']}")
    for k, v in chain.items():
        if k.startswith('Notional_') or k.startswith('Quantity_'):
            print(f"{k}: {v}")
    print("-" * 50)

# Save open chains to a new CSV in the CWD with a name based on the input file
base_name = os.path.splitext(os.path.basename(csv_file))[0]
output_file = os.path.join(cwd, f'open_{base_name}.csv')
open_chains_df = pd.DataFrame(open_chains)
open_chains_df.to_csv(output_file, index=False)
print(f"Open chains saved to '{output_file}' in the current working directory")

# Function to aggregate notional data by date and currency for non-basket entries
def aggregate_notional_by_currency(df):
    non_basket_df = df[df['Product name'] != 'Equity:Swap:PriceReturnBasicPerformance:Basket'].copy()
    if non_basket_df.empty:
        logging.info("No non-basket entries found for notional aggregation.")
        return None
    
    non_basket_df.loc[:, 'Product name'] = non_basket_df['Product name'].fillna('').astype(str)
    non_basket_df.loc[:, 'Notional amount-Leg 1'] = pd.to_numeric(non_basket_df.iloc[:, 19], errors='coerce').fillna(0)
    non_basket_df.loc[:, 'Total notional quantity-Leg 1'] = pd.to_numeric(non_basket_df.iloc[:, 25], errors='coerce').fillna(0)
    currency_series = non_basket_df.iloc[:, 21].fillna('').astype(str).str.strip().str.upper()
    non_basket_df.loc[:, 'Currency'] = currency_series
    
    date_aggregates = defaultdict(lambda: {'count': 0, 'notional': defaultdict(float), 'quantity': defaultdict(float)})
    for _, row in non_basket_df.iterrows():
        exec_date = pd.to_datetime(row['Execution Timestamp'], errors='coerce').date()
        notional = row['Notional amount-Leg 1']
        quantity = row['Total notional quantity-Leg 1']
        currency = row['Currency'] if row['Currency'] else 'UNK'
        date_aggregates[exec_date]['count'] += 1
        if notional > 0:
            date_aggregates[exec_date]['notional'][currency] += notional
        if quantity > 0:
            date_aggregates[exec_date]['quantity'][currency] += quantity
    
    result_data = []
    currencies = set()
    for date, data in date_aggregates.items():
        row = {'Date': date, 'Count': data['count']}
        for currency in data['notional'].keys():
            currencies.add(currency)
            row[f'Notional_{currency}'] = data['notional'][currency]
            row[f'Quantity_{currency}'] = data['quantity'].get(currency, 0)
        result_data.append(row)
    
    if not result_data:
        return None
    columns = ['Date', 'Count'] + [f'Notional_{c}' for c in sorted(currencies)] + [f'Quantity_{c}' for c in sorted(currencies)]
    return pd.DataFrame(result_data, columns=columns)

# Prompt for charting
chart_prompt = input("\nChart the execution dates? (yes/no): ").strip().lower()
if chart_prompt == 'yes':
    # Filter for NEWT trades only using loc to avoid SettingWithCopyWarning
    newt_df = df.loc[df['Action type'] == 'NEWT'].copy()
    
    # Convert Execution Timestamp to datetime with error handling
    newt_df.loc[:, 'Execution Timestamp'] = pd.to_datetime(newt_df['Execution Timestamp'], errors='coerce', utc=True)
    invalid_timestamps = newt_df['Execution Timestamp'].isna().sum()
    print(f"Number of invalid/missing Execution Timestamp values: {invalid_timestamps}")
    if invalid_timestamps > 0:
        print("Warning: Some Execution Timestamp values could not be converted to datetime and are set to NaT.")
    
    # Extract date only for valid timestamps
    newt_df.loc[:, 'Execution Date'] = newt_df['Execution Timestamp'].apply(lambda x: x.date() if pd.notna(x) else None)
    
    # Ensure Product name is string and handle NaN
    newt_df.loc[:, 'Product name'] = newt_df['Product name'].fillna('').astype(str)
    
    # Group by date to count NEWT trades for all trades
    all_volume = newt_df.groupby('Execution Date').size().reset_index(name='Contract Volume')
    all_volume = all_volume.dropna(subset=['Execution Date'])  # Drop rows with None dates
    all_volume['Execution Date'] = pd.to_datetime(all_volume['Execution Date'])
    
    # Filter for CFD trades with string check
    cfd_df = newt_df[newt_df['Product name'].str.contains('ContractForDifference', na=False, case=False, regex=True)]
    cfd_volume = cfd_df.groupby('Execution Date').size().reset_index(name='Contract Volume')
    cfd_volume = cfd_volume.dropna(subset=['Execution Date'])
    cfd_volume['Execution Date'] = pd.to_datetime(cfd_volume['Execution Date'])
    
    # Filter for non-CFD trades (excluding basket swaps for notional, but included in count)
    non_cfd_df = newt_df[~newt_df['Product name'].str.contains('ContractForDifference', na=False, case=False, regex=True)]
    non_cfd_volume = non_cfd_df.groupby('Execution Date').size().reset_index(name='Contract Volume')
    non_cfd_volume = non_cfd_volume.dropna(subset=['Execution Date'])
    non_cfd_volume['Execution Date'] = pd.to_datetime(non_cfd_volume['Execution Date'])
    
    # Aggregate notional data for non-basket entries
    notional_df = aggregate_notional_by_currency(newt_df)
    if notional_df is not None:
        print(f"Debug: notional_df content:\n{notional_df}")  # Debug output to verify data

    # Create Matplotlib bar charts
    # All Trades Chart
    plt.figure(figsize=(10, 6), num='All Trades Volume')  # Set window title
    bars = plt.bar(all_volume['Execution Date'], all_volume['Contract Volume'])
    plt.title(f'Volume of All NEWT Trades Per Day ({base_name})')
    plt.xlabel('Execution Date')
    plt.ylabel('Number of NEWT Trades')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    cursor = mplcursors.cursor(bars, hover=True)
    @cursor.connect("add")
    def on_add(sel):
        idx = sel.index
        print(f"Hover index for All Trades: {idx}, Type: {type(idx)}")
        sel.annotation.set_text(f'Date: {all_volume["Execution Date"][idx].date()}\nTrades: {all_volume["Contract Volume"][idx]}')
        sel.annotation.get_bbox_patch().set_fc('white')
        sel.annotation.get_bbox_patch().set_alpha(0.8)
    
    all_chart_file = os.path.join(cwd, f'all_volume_newt_{base_name}.png')
    plt.savefig(all_chart_file)
    plt.show()
    print(f"All trades chart saved to '{all_chart_file}'")
    
    # CFD Trades Chart
    plt.figure(figsize=(10, 6), num='CFD Trades Volume')  # Set window title
    bars = plt.bar(cfd_volume['Execution Date'], cfd_volume['Contract Volume'])
    plt.title(f'Volume of NEWT CFD Trades Per Day ({base_name})')
    plt.xlabel('Execution Date')
    plt.ylabel('Number of NEWT CFD Trades')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    cursor = mplcursors.cursor(bars, hover=True)
    @cursor.connect("add")
    def on_add(sel):
        idx = sel.index
        print(f"Hover index for CFD: {idx}, Type: {type(idx)}")
        sel.annotation.set_text(f'Date: {cfd_volume["Execution Date"][idx].date()}\nTrades: {cfd_volume["Contract Volume"][idx]}')
        sel.annotation.get_bbox_patch().set_fc('white')
        sel.annotation.get_bbox_patch().set_alpha(0.8)
    
    cfd_chart_file = os.path.join(cwd, f'cfd_volume_newt_{base_name}.png')
    plt.savefig(cfd_chart_file)
    plt.show()
    print(f"CFD trades chart saved to '{cfd_chart_file}'")
    
    # Non-CFD Trades Chart
    plt.figure(figsize=(10, 6), num='Non-CFD Trades Volume')  # Set window title
    bars = plt.bar(non_cfd_volume['Execution Date'], non_cfd_volume['Contract Volume'])
    plt.title(f'Volume of NEWT Non-CFD Trades Per Day ({base_name})')
    plt.xlabel('Execution Date')
    plt.ylabel('Number of NEWT Non-CFD Trades')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    cursor = mplcursors.cursor(bars, hover=True)
    @cursor.connect("add")
    def on_add(sel):
        idx = sel.index
        print(f"Hover index for Non-CFD: {idx}, Type: {type(idx)}")
        sel.annotation.set_text(f'Date: {non_cfd_volume["Execution Date"][idx].date()}\nTrades: {non_cfd_volume["Contract Volume"][idx]}')
        sel.annotation.get_bbox_patch().set_fc('white')
        sel.annotation.get_bbox_patch().set_alpha(0.8)
    
    non_cfd_chart_file = os.path.join(cwd, f'non_cfd_volume_newt_{base_name}.png')
    plt.savefig(non_cfd_chart_file)
    plt.show()
    print(f"Non-CFD trades chart saved to '{non_cfd_chart_file}'")
    
    # Notional Chart for Non-Basket Entries
    if notional_df is not None and not notional_df.empty:
        plt.figure(figsize=(12, 6), num='Notional Amounts')  # Set window title
        dates = notional_df['Date'].values  # Use notional_df dates for x-axis
        bars = []  # Store bar objects for cursor
        for currency in [col for col in notional_df.columns if col.startswith('Notional_')]:
            curr_data = notional_df[currency].values  # Use the currency column directly
            if len(curr_data) == len(dates):  # Ensure alignment
                bars.extend(plt.bar(dates, curr_data, label=currency.replace('Notional_', '')).flatten())  # Flatten bar list
        
        plt.title(f'Notional Amounts for Non-Basket NEWT Trades Per Day ({base_name})')
        plt.xlabel('Execution Date')
        plt.ylabel('Notional Amount')
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        
        # Use mplcursors with hover data including notional and quantity
        if bars:  # Only create cursor if bars exist
            print(f"Number of bars plotted: {len(bars)}")  # Debug bar count
            cursor = mplcursors.cursor(bars, hover=True)
            @cursor.connect("add")
            def on_add(sel):
                idx = sel.target.index  # Use the bar's index from the plot
                print(f"Hover index for Notional: {idx}, Type: {type(idx)}")  # Debug index
                # Get the date from the x-axis
                date = pd.to_datetime(dates[idx]).date() if 0 <= idx < len(dates) else 'Unknown'
                # Find the corresponding row in notional_df
                row_idx = notional_df.index[notional_df['Date'] == date].tolist()
                if row_idx:
                    row_idx = row_idx[0]
                    notional_text = '\n'.join([f'{c.replace("Notional_", "")}: {notional_df[c].iloc[row_idx]:.2f}' 
                                              for c in notional_df.columns if c.startswith('Notional_') 
                                              and not pd.isna(notional_df[c].iloc[row_idx])])
                    quantity_text = '\n'.join([f'{c.replace("Quantity_", "")}: {notional_df[c].iloc[row_idx]:.2f}' 
                                              for c in notional_df.columns if c.startswith('Quantity_') 
                                              and not pd.isna(notional_df[c].iloc[row_idx])])
                else:
                    notional_text = ''
                    quantity_text = ''
                hover_text = f'Date: {date}\n{notional_text}\n{quantity_text}'
                if not notional_text and not quantity_text:
                    hover_text = f'Date: {date}\nNo notional or quantity data available'
                sel.annotation.set_text(hover_text)
                sel.annotation.get_bbox_patch().set_fc('white')
                sel.annotation.get_bbox_patch().set_alpha(0.8)
        else:
            print("No bars plotted for notional chart, skipping cursor.")

        notional_chart_file = os.path.join(cwd, f'notional_non_basket_newt_{base_name}.png')
        plt.savefig(notional_chart_file)
        plt.show()
        print(f"Notional chart for non-basket trades saved to '{notional_chart_file}'")
    else:
        print("No notional data available for non-basket entries.")

print("Note: Notional amounts and quantities are calculated for all non-basket swap entries (excluding Equity:Swap:PriceReturnBasicPerformance:Basket) due to unclear weighting information for basket swaps.")
