import pandas as pd
import os
import matplotlib.pyplot as plt
import mplcursors
from collections import defaultdict
import logging
from datetime import datetime

# Function to print timestamped console messages
def log_to_console(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

# Get the current working directory
cwd = os.getcwd()
log_to_console(f"Current working directory: {cwd}")

# List all subdirectories in the CWD
log_to_console("Scanning for subdirectories...")
subdirs = [d for d in os.listdir(cwd) if os.path.isdir(os.path.join(cwd, d))]

if not subdirs:
    log_to_console("ERROR: No subdirectories found in the current directory.")
    exit(1)

# Print numbered list of subdirectories
log_to_console("Available subdirectories found:")
for i, subdir in enumerate(subdirs, 1):
    print(f"{i}. {subdir}")

# Get user selection for subdirectory
subdir_selection = int(input("Select a subdirectory by number: "))
if subdir_selection < 1 or subdir_selection > len(subdirs):
    log_to_console(f"ERROR: Invalid subdirectory selection: {subdir_selection}")
    exit(1)

# Get the selected subdirectory path
selected_subdir = subdirs[subdir_selection - 1]
subdir_path = os.path.join(cwd, selected_subdir)
log_to_console(f"Selected subdirectory: {selected_subdir}")

# List all CSV files in the selected subdirectory
log_to_console(f"Scanning for CSV files in '{selected_subdir}'...")
csv_files = [f for f in os.listdir(subdir_path) if f.endswith('.csv')]

if not csv_files:
    log_to_console(f"ERROR: No CSV files found in the subdirectory '{selected_subdir}'.")
    exit(1)

# Print numbered list of CSV files
log_to_console(f"Available CSV files in '{selected_subdir}':")
for i, file in enumerate(csv_files, 1):
    print(f"{i}. {file}")

# Get user selection for CSV file
csv_selection = int(input("Select a CSV file by number: "))
if csv_selection < 1 or csv_selection > len(csv_files):
    log_to_console(f"ERROR: Invalid CSV file selection: {csv_selection}")
    exit(1)

# Load the selected CSV
csv_file = os.path.join(subdir_path, csv_files[csv_selection - 1])
log_to_console(f"Loading CSV file: {csv_file}")
df = pd.read_csv(csv_file, low_memory=False)
log_to_console(f"CSV file loaded successfully. Number of rows: {len(df)}")

# Set up logging to file
log_file = os.path.join(cwd, 'swap_analysis_all.log')
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log_to_console(f"Logging initialized to file: {log_file}")

# Ensure 'Dissemination Identifier' and 'Original Dissemination Identifier' are treated as strings
log_to_console("Converting 'Dissemination Identifier' and 'Original Dissemination Identifier' to strings...")
df['Dissemination Identifier'] = df['Dissemination Identifier'].astype(str)
df['Original Dissemination Identifier'] = df['Original Dissemination Identifier'].astype(str).replace('nan', '')
log_to_console("String conversion completed.")

# Function to aggregate notional and quantity by currency for all entries
def aggregate_notional_by_currency(df):
    log_to_console("Aggregating notional and quantity data by currency...")
    non_basket_df = df[df['Product name'] != 'Equity:Swap:PriceReturnBasicPerformance:Basket'].copy()
    if non_basket_df.empty:
        log_to_console("No non-basket entries found for notional aggregation.")
        logging.info("No non-basket entries found for notional aggregation.")
        return None
    
    log_to_console("Converting notional and quantity columns to numeric...")
    non_basket_df.loc[:, 'Notional amount-Leg 1'] = pd.to_numeric(non_basket_df.iloc[:, 19], errors='coerce').fillna(0)
    non_basket_df.loc[:, 'Total notional quantity-Leg 1'] = pd.to_numeric(non_basket_df.iloc[:, 25], errors='coerce').fillna(0)
    currency_series = non_basket_df.iloc[:, 21].fillna('').astype(str).str.strip().str.upper()
    non_basket_df.loc[:, 'Currency'] = currency_series
    log_to_console("Conversion to numeric completed.")
    
    date_aggregates = defaultdict(lambda: {'count': 0, 'notional': defaultdict(float), 'quantity': defaultdict(float)})
    log_to_console("Aggregating data by execution date and currency...")
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
        log_to_console("No aggregated data available for notional and quantity.")
        return None
    columns = ['Date', 'Count'] + [f'Notional_{c}' for c in sorted(currencies)] + [f'Quantity_{c}' for c in sorted(currencies)]
    log_to_console("Notional and quantity aggregation completed.")
    return pd.DataFrame(result_data, columns=columns)

# Process all transactions (NEWT, MODI, TERM)
log_to_console("Processing all transactions (NEWT, MODI, TERM)...")
all_positions = []
for idx, row in df.iterrows():
    all_positions.append({
        'Dissemination ID': row['Dissemination Identifier'],
        'Action Type': row['Action type'],
        'Event Timestamp': pd.to_datetime(row['Event timestamp'], errors='coerce', format='%Y-%m-%dT%H:%M:%SZ'),
        'Execution Timestamp': pd.to_datetime(row['Execution Timestamp'], errors='coerce'),
        'Expiration Date': pd.to_datetime(row['Expiration Date'], errors='coerce'),
        'Swap Type': row['Product name'],
        'Notional Amount': pd.to_numeric(row.iloc[19], errors='coerce') if row['Product name'] != 'Equity:Swap:PriceReturnBasicPerformance:Basket' else 0,
        'Notional Currency': row.iloc[21] if row['Product name'] != 'Equity:Swap:PriceReturnBasicPerformance:Basket' else 'N/A',
        'Quantity': pd.to_numeric(row.iloc[25], errors='coerce') if row['Product name'] != 'Equity:Swap:PriceReturnBasicPerformance:Basket' else 0
    })
log_to_console(f"Processed {len(all_positions)} transactions.")

# Convert to DataFrame and save
log_to_console("Converting processed transactions to DataFrame...")
all_positions_df = pd.DataFrame(all_positions)
output_file = os.path.join(cwd, f'all_positions_{os.path.splitext(os.path.basename(csv_file))[0]}.csv')
log_to_console(f"Saving all positions to '{output_file}'...")
all_positions_df.to_csv(output_file, index=False)
log_to_console(f"All positions saved successfully to '{output_file}'.")

# Suppress warnings for cleaner output
import warnings
warnings.filterwarnings('ignore', category=UserWarning)  # Suppress timezone warning
pd.options.mode.chained_assignment = None  # Suppress SettingWithCopyWarning
import matplotlib.pyplot as plt
import mplcursors

def chart_all_expiries(df_chart, ticker, date_label, period, csv_file, cwd):
    log_to_console(f"Preparing to chart all swaps' {period} expiries based on {date_label}...")
    # Prepare data for charting all expiries
    df_chart = df_chart.copy()
    # Clean Swap Type column
    log_to_console("Cleaning Swap Type column for all expiries...")
    df_chart['Swap Type'] = df_chart['Swap Type'].fillna('Unknown').astype(str)
    log_to_console(f"Unique Swap Type values: {df_chart['Swap Type'].unique().tolist()}")
    
    df_chart['Expiration Date'] = pd.to_datetime(df_chart['Expiration Date'], errors='coerce')
    invalid_dates = df_chart['Expiration Date'].isna().sum()
    log_to_console(f"Number of invalid/missing {date_label} values: {invalid_dates}")
    if invalid_dates > 0:
        log_to_console(f"Warning: Dropping {invalid_dates} rows with invalid {date_label} values.")
    df_chart = df_chart.dropna(subset=['Expiration Date'])
    if period == 'daily':
        df_chart['Period'] = df_chart['Expiration Date'].dt.to_period('D')
        date_format = '%Y-%m-%d'
    elif period == 'weekly':
        df_chart['Period'] = df_chart['Expiration Date'].dt.to_period('W')
        date_format = '%Y-W%W'
    else:  # monthly
        df_chart['Period'] = df_chart['Expiration Date'].dt.to_period('M')
        date_format = '%b %Y'
    df_chart['Period'] = df_chart['Period'].dt.to_timestamp()
    log_to_console(f"Data prepared. Number of valid rows for charting: {len(df_chart)}")
    
    if df_chart.empty:
        log_to_console("ERROR: No valid data available for charting after filtering. Skipping chart generation.")
        print("No data to chart. Please check the input CSV for valid Expiration Date values.")
        return
    
    # Get all unique action types for hover data
    log_to_console("Identifying unique action types for hover data...")
    action_types = df_chart['Action Type'].unique().tolist()
    log_to_console(f"Unique action types: {action_types}")
    
    # Group by period and action type for counts
    log_to_console(f"Grouping data by {period} and action type for counts...")
    volume_by_action = df_chart.groupby(['Period', 'Action Type']).size().unstack(fill_value=0)
    volume_by_action = volume_by_action.reset_index()
    volume_by_action.rename(columns={'Period': 'MonthYear'}, inplace=True)
    log_to_console(f"Grouped data for counts. Unique {period}s: {len(volume_by_action)}")
    
    if volume_by_action.empty:
        log_to_console("ERROR: No grouped data available for charting. Skipping chart generation.")
        print("No grouped data to chart. Please ensure the CSV contains valid action types.")
        return
    
    # Ensure NEWT, MODI, TERM columns exist for plotting
    log_to_console("Ensuring columns for NEWT, MODI, TERM exist for plotting...")
    for action in ['NEWT', 'MODI', 'TERM']:
        if action not in volume_by_action.columns:
            volume_by_action[action] = 0
            log_to_console(f"Added missing column for {action} with zero values.")
    
    # Aggregate notional amounts by period and action type
    log_to_console(f"Aggregating notional amounts by {period} and action type...")
    notional_by_action = df_chart[df_chart['Notional Amount'] > 0].groupby(['Period', 'Action Type'])['Notional Amount'].sum().unstack(fill_value=0)
    notional_by_action = notional_by_action.reset_index()
    notional_by_action.rename(columns={'Period': 'MonthYear'}, inplace=True)
    for action in action_types:
        if action not in notional_by_action.columns:
            notional_by_action[action] = 0
            log_to_console(f"Added missing notional column for {action} with zero values.")
    log_to_console("Notional aggregation completed.")
    
    # Aggregate swap type counts by period
    log_to_console(f"Aggregating swap type counts by {period}...")
    swap_type_counts = df_chart.groupby(['Period', 'Swap Type']).size().unstack(fill_value=0)
    swap_type_counts = swap_type_counts.reset_index()
    swap_type_counts.rename(columns={'Period': 'MonthYear'}, inplace=True)
    for col in swap_type_counts.columns:
        if col != 'MonthYear':
            swap_type_counts[col] = pd.to_numeric(swap_type_counts[col], errors='coerce').fillna(0).astype(int)
    log_to_console(f"Swap type counts aggregated. Unique swap types: {len(swap_type_counts.columns) - 1}")
    
    # Define swap_types before merging
    swap_types = [col for col in swap_type_counts.columns if col != 'MonthYear']
    log_to_console(f"Defined swap type columns before merge: {swap_types}")
    
    # Merge dataframes to align month/years
    log_to_console("Merging count, notional, and swap type data...")
    merged_data = volume_by_action.merge(notional_by_action, on='MonthYear', how='left', suffixes=('', '_notional'))
    merged_data = merged_data.merge(swap_type_counts, on='MonthYear', how='left')
    merged_data.fillna(0, inplace=True)
    log_to_console(f"Data merging completed. Merged data shape: {merged_data.shape}")
    
    # Fetch stock price data for overlay (if ticker provided)
    if ticker:
        log_to_console(f"Fetching historical monthly stock data for {ticker}...")
        try:
            import yfinance as yf
            stock_data = yf.download(ticker, start=merged_data['MonthYear'].min().strftime('%Y-%m-%d'), 
                                    end=merged_data['MonthYear'].max().strftime('%Y-%m-%d'), interval='1mo', auto_adjust=False)
            if not stock_data.empty:
                if stock_data.columns.nlevels > 1:
                    stock_data.columns = stock_data.columns.get_level_values(0)
                    log_to_console(f"Flattened MultiIndex columns. Available columns: {list(stock_data.columns)}")
                else:
                    log_to_console(f"Available columns: {list(stock_data.columns)}")
                
                price_column = next((col for col in ['Close', 'close', 'Adj Close', 'adj_close'] if col in stock_data.columns), None)
                if price_column is None:
                    raise ValueError(f"No valid price column found in yfinance data. Available columns: {list(stock_data.columns)}")
                log_to_console(f"Found price column: {price_column}")
                
                stock_data = stock_data[[price_column]].reset_index()
                stock_data.rename(columns={price_column: 'Close'}, inplace=True)
                stock_data['MonthYear'] = pd.to_datetime(stock_data['Date']).dt.to_period('M').dt.to_timestamp()
                merged_data = merged_data.merge(stock_data[['MonthYear', 'Close']], on='MonthYear', how='left')
                merged_data['Close'].fillna(method='ffill', inplace=True)
                log_to_console(f"Stock data fetched successfully. Price range: ${merged_data['Close'].min():.2f} - ${merged_data['Close'].max():.2f}")
            else:
                raise ValueError("No stock data returned from Yahoo Finance")
        except Exception as e:
            log_to_console(f"Error fetching stock data: {str(e)}. Skipping price overlay.")
            merged_data['Close'] = 0
    else:
        merged_data['Close'] = 0
        log_to_console("No ticker provided; skipping stock price overlay.")
    
    # Log swap type columns for debugging
    swap_types = [col for col in swap_types if col in merged_data.columns]
    log_to_console(f"Swap type columns after merge: {swap_types}")
    
    # Create bar chart with stock price overlay
    log_to_console(f"Generating bar chart with stock price overlay for all {period} expiries...")
    fig, ax1 = plt.subplots(figsize=(12, 6), num=f'All {date_label} {period.capitalize()} Volume by Action Type with {ticker or "No"} Price Overlay')
    bar_width = 0.25
    month_years = merged_data['MonthYear']
    index = range(len(month_years))
    
    bars_newt = ax1.bar([i - bar_width for i in index], merged_data['NEWT'], bar_width, label='NEWT', color='blue')
    bars_modi = ax1.bar(index, merged_data['MODI'], bar_width, label='MODI', color='green')
    bars_term = ax1.bar([i + bar_width for i in index], merged_data['TERM'], bar_width, label='TERM', color='red')
    
    ax1.set_xlabel(f'{date_label} ({period.capitalize()})')
    ax1.set_ylabel('Number of Actions', color='black')
    ax1.tick_params(axis='y', labelcolor='black')
    plt.xticks(index, month_years.dt.strftime(date_format), rotation=45 if period == 'daily' else 90)
    ax1.legend(loc='upper left')
    
    if ticker and 'Close' in merged_data.columns and merged_data['Close'].max() > 0:
        ax2 = ax1.twinx()
        trendline, = ax2.plot(index, merged_data['Close'], color='orange', marker='o', linewidth=2, label=f'{ticker} Close Price')
        ax2.set_ylabel(f'{ticker} Closing Price ($)', color='orange')
        ax2.tick_params(axis='y', labelcolor='orange')
        ax2.legend(loc='upper right')
        log_to_console("Stock price line added to secondary axis.")
    else:
        log_to_console("No valid stock price data; skipping overlay.")
    
    plt.title(f'Volume of NEWT, MODI, and TERM Actions by All {date_label} {period.capitalize()} with {ticker or "No"} Price Overlay ({os.path.splitext(os.path.basename(csv_file))[0]})')
    plt.tight_layout()
    log_to_console("Bar chart with overlay created successfully.")
    
    # Add hover functionality for both bars and trendline
    log_to_console("Adding hover functionality to chart...")
    try:
        cursor = mplcursors.cursor([bars_newt, bars_modi, bars_term, trendline], hover=True)
        @cursor.connect("add")
        def on_add(sel):
            try:
                idx = int(sel.index)
                log_to_console(f"Hover event at index: {idx}")
                
                if idx < 0 or idx >= len(merged_data):
                    log_to_console(f"Invalid hover index: {idx}. Skipping tooltip.")
                    sel.annotation.set_text("Invalid index for hover data")
                    return
                
                month_year = merged_data['MonthYear'].iloc[idx].strftime(date_format)
                stock_price = merged_data.get('Close', pd.Series([0] * len(merged_data))).iloc[idx]
                
                is_trendline = sel.artist == trendline if ticker and 'Close' in merged_data.columns and merged_data['Close'].max() > 0 else False
                
                action_text = []
                for action in action_types:
                    try:
                        count = merged_data.get(action, pd.Series([0] * len(merged_data))).iloc[idx]
                        notional = merged_data.get(f'{action}_notional', pd.Series([0] * len(merged_data))).iloc[idx]
                        if pd.notna(count) and count > 0:
                            action_text.append(f"{action}: {int(count)} (Notional: ${notional:,.2f})")
                        else:
                            log_to_console(f"Skipping action type '{action}' at index {idx}: count is {count}")
                    except Exception as e:
                        log_to_console(f"Error processing action type '{action}' at index {idx}: {str(e)}")
                
                swap_type_text = []
                for col in swap_types:
                    try:
                        value = merged_data.at[idx, col]
                        if pd.notna(value) and value > 0:
                            swap_type_text.append(f"{col}: {int(value)}")
                        else:
                            log_to_console(f"Skipping swap type column '{col}' at index {idx}: value is {value}")
                    except Exception as e:
                        log_to_console(f"Error processing swap type column '{col}' at index {idx}: {str(e)}")
                
                action_text = '\n'.join(action_text) if action_text else 'None'
                swap_type_text = '\n'.join(swap_type_text) if swap_type_text else 'None'
                log_to_console(f"Action text for index {idx}: {action_text}")
                log_to_console(f"Swap type text for index {idx}: {swap_type_text}")
                
                if is_trendline:
                    hover_text = f"{date_label} ({period.capitalize()}): {month_year}\n"
                    if stock_price > 0:
                        hover_text += f"{ticker} Close: ${stock_price:,.2f}\n"
                    if action_text != 'None' or swap_type_text != 'None':
                        hover_text += f"Actions:\n{action_text}\n" if action_text != 'None' else ''
                        hover_text += f"Swap Types:\n{swap_type_text}" if swap_type_text != 'None' else ''
                else:
                    hover_text = f"{date_label} ({period.capitalize()}): {month_year}\n"
                    hover_text += f"Actions:\n{action_text}\n" if action_text != 'None' else ''
                    if ticker and stock_price > 0:
                        hover_text += f"{ticker} Close: ${stock_price:,.2f}\n"
                    hover_text += f"Swap Types:\n{swap_type_text}" if swap_type_text != 'None' else ''
                
                sel.annotation.set_text(hover_text)
                sel.annotation.get_bbox_patch().set_fc('white')
                sel.annotation.get_bbox_patch().set_alpha(0.8)
            except Exception as e:
                log_to_console(f"Error in hover callback at index {idx}: {str(e)}")
                sel.annotation.set_text("Error displaying hover data")
        log_to_console("Hover functionality added.")
    except Exception as e:
        log_to_console(f"Error setting up mplcursors: {str(e)}")
        print("Warning: Hover functionality could not be added due to an error. Chart will still be displayed.")
    
    chart_file = os.path.join(cwd, f'all_action_volume_{date_label.lower().replace(" ", "_")}_{period}_{"with_" + ticker.lower() if ticker else "no"}_overlay_{os.path.splitext(os.path.basename(csv_file))[0]}.png')
    log_to_console(f"Saving chart to '{chart_file}'...")
    try:
        plt.savefig(chart_file)
        log_to_console("Chart saved successfully.")
    except Exception as e:
        log_to_console(f"Error saving chart: {str(e)}")
        print(f"Warning: Could not save chart to '{chart_file}'. Displaying chart only.")
    
    try:
        plt.show()
        log_to_console("Chart displayed successfully.")
    except Exception as e:
        log_to_console(f"Error displaying chart: {str(e)}")
        print("Error: Could not display chart. Please check the Matplotlib backend configuration.")

# Main charting logic
chart_prompt = input("\nChart the data? (yes/no): ").strip().lower()
log_to_console(f"User chart prompt response: {chart_prompt}")
if chart_prompt == 'yes':
    # Prompt for execution or expiration dates
    log_to_console("Prompting user for date type selection...")
    date_type = input("Plot charts based on (1) Execution Dates or (2) Expiration Dates? Enter 1 or 2: ").strip()
    log_to_console(f"User selected date type: {date_type}")
    if date_type not in ['1', '2']:
        log_to_console("Invalid date type selection. Defaulting to Execution Dates.")
        date_type = '1'
    
    date_column = 'Execution Timestamp' if date_type == '1' else 'Expiration Date'
    date_label = 'Execution Date' if date_type == '1' else 'Expiration Date'
    log_to_console(f"Using {date_label} for charting (column: {date_column}).")
    
    # Prompt for aggregation period
    log_to_console("Prompting user for aggregation period...")
    period = input("Daily, weekly, or monthly aggregation? (daily/weekly/monthly): ").strip().lower()
    log_to_console(f"User selected aggregation period: {period}")
    if period not in ['daily', 'weekly', 'monthly']:
        log_to_console("Invalid aggregation period selection. Defaulting to monthly.")
        period = 'monthly'
    
    # Prompt for expiry type (only for expiration dates)
    if date_type == '2':
        expiry_type = input("Open swap expiries or all swaps' expiries? (open/all): ").strip().lower()
        log_to_console(f"User selected expiry type: {expiry_type}")
        if expiry_type not in ['open', 'all']:
            log_to_console("Invalid expiry type selection. Defaulting to open swap expiries.")
            expiry_type = 'open'
    else:
        expiry_type = 'open'  # Default for execution dates
    
    # Prompt for stock ticker (last step)
    ticker = input("Enter stock ticker for price overlay (e.g., GME): ").strip()
    if not ticker:
        log_to_console("No ticker provided. Proceeding without stock price overlay.")
        ticker = None
    else:
        log_to_console(f"Using ticker '{ticker}' for price overlay.")
    
    # Prepare data for charting
    log_to_console(f"Preparing data for charting based on {date_label} with {period} aggregation...")
    df_chart = all_positions_df.copy()
    
    if expiry_type == 'open' or date_type == '1':
        # Clean Swap Type column
        log_to_console("Cleaning Swap Type column...")
        df_chart['Swap Type'] = df_chart['Swap Type'].fillna('Unknown').astype(str)
        log_to_console(f"Unique Swap Type values: {df_chart['Swap Type'].unique().tolist()}")
        
        df_chart[date_column] = pd.to_datetime(df_chart[date_column], errors='coerce')
        invalid_dates = df_chart[date_column].isna().sum()
        log_to_console(f"Number of invalid/missing {date_label} values: {invalid_dates}")
        if invalid_dates > 0:
            log_to_console(f"Warning: Dropping {invalid_dates} rows with invalid {date_label} values.")
        df_chart = df_chart.dropna(subset=[date_column])
        if period == 'daily':
            df_chart['MonthYear'] = df_chart[date_column].dt.to_period('D')
            date_format = '%Y-%m-%d'
        elif period == 'weekly':
            df_chart['MonthYear'] = df_chart[date_column].dt.to_period('W')
            date_format = '%Y-W%W'
        else:  # monthly
            df_chart['MonthYear'] = df_chart[date_column].dt.to_period('M')
            date_format = '%b %Y'
        df_chart['MonthYear'] = df_chart['MonthYear'].dt.to_timestamp()
        log_to_console(f"Data prepared. Number of valid rows for charting: {len(df_chart)}")
        
        if df_chart.empty:
            log_to_console("ERROR: No valid data available for charting after filtering. Skipping chart generation.")
            print("No data to chart. Please check the input CSV for valid Execution Timestamp or Expiration Date values.")
            exit(1)
        
        # Get all unique action types for hover data
        log_to_console("Identifying unique action types for hover data...")
        action_types = df_chart['Action Type'].unique().tolist()
        log_to_console(f"Unique action types: {action_types}")
        
        # Group by period and action type for counts
        log_to_console(f"Grouping data by {period} and action type for counts...")
        volume_by_action = df_chart.groupby(['MonthYear', 'Action Type']).size().unstack(fill_value=0)
        volume_by_action = volume_by_action.reset_index()
        log_to_console(f"Grouped data for counts. Unique {period}s: {len(volume_by_action)}")
        
        if volume_by_action.empty:
            log_to_console("ERROR: No grouped data available for charting. Skipping chart generation.")
            print("No grouped data to chart. Please ensure the CSV contains valid action types.")
            exit(1)
        
        # Ensure NEWT, MODI, TERM columns exist for plotting
        log_to_console("Ensuring columns for NEWT, MODI, TERM exist for plotting...")
        for action in ['NEWT', 'MODI', 'TERM']:
            if action not in volume_by_action.columns:
                volume_by_action[action] = 0
                log_to_console(f"Added missing column for {action} with zero values.")
        
        # Aggregate notional amounts by period and action type
        log_to_console(f"Aggregating notional amounts by {period} and action type...")
        notional_by_action = df_chart[df_chart['Notional Amount'] > 0].groupby(['MonthYear', 'Action Type'])['Notional Amount'].sum().unstack(fill_value=0)
        notional_by_action = notional_by_action.reset_index()
        for action in action_types:
            if action not in notional_by_action.columns:
                notional_by_action[action] = 0
                log_to_console(f"Added missing notional column for {action} with zero values.")
        log_to_console("Notional aggregation completed.")
        
        # Aggregate swap type counts by period
        log_to_console(f"Aggregating swap type counts by {period}...")
        swap_type_counts = df_chart.groupby(['MonthYear', 'Swap Type']).size().unstack(fill_value=0)
        swap_type_counts = swap_type_counts.reset_index()
        for col in swap_type_counts.columns:
            if col != 'MonthYear':
                swap_type_counts[col] = pd.to_numeric(swap_type_counts[col], errors='coerce').fillna(0).astype(int)
        log_to_console(f"Swap type counts aggregated. Unique swap types: {len(swap_type_counts.columns) - 1}")
        
        # Define swap_types before merging
        swap_types = [col for col in swap_type_counts.columns if col != 'MonthYear']
        log_to_console(f"Defined swap type columns before merge: {swap_types}")
        
        # Merge dataframes to align month/years
        log_to_console("Merging count, notional, and swap type data...")
        merged_data = volume_by_action.merge(notional_by_action, on='MonthYear', how='left', suffixes=('', '_notional'))
        merged_data = merged_data.merge(swap_type_counts, on='MonthYear', how='left')
        merged_data.fillna(0, inplace=True)
        log_to_console(f"Data merging completed. Merged data shape: {merged_data.shape}")
        
        # Fetch stock price data for overlay (if ticker provided)
        if ticker:
            log_to_console(f"Fetching historical monthly stock data for {ticker}...")
            try:
                import yfinance as yf
                stock_data = yf.download(ticker, start=merged_data['MonthYear'].min().strftime('%Y-%m-%d'), 
                                        end=merged_data['MonthYear'].max().strftime('%Y-%m-%d'), interval='1mo', auto_adjust=False)
                if not stock_data.empty:
                    if stock_data.columns.nlevels > 1:
                        stock_data.columns = stock_data.columns.get_level_values(0)
                        log_to_console(f"Flattened MultiIndex columns. Available columns: {list(stock_data.columns)}")
                    else:
                        log_to_console(f"Available columns: {list(stock_data.columns)}")
                    
                    price_column = next((col for col in ['Close', 'close', 'Adj Close', 'adj_close'] if col in stock_data.columns), None)
                    if price_column is None:
                        raise ValueError(f"No valid price column found in yfinance data. Available columns: {list(stock_data.columns)}")
                    log_to_console(f"Found price column: {price_column}")
                    
                    stock_data = stock_data[[price_column]].reset_index()
                    stock_data.rename(columns={price_column: 'Close'}, inplace=True)
                    stock_data['MonthYear'] = pd.to_datetime(stock_data['Date']).dt.to_period('M').dt.to_timestamp()
                    merged_data = merged_data.merge(stock_data[['MonthYear', 'Close']], on='MonthYear', how='left')
                    merged_data['Close'].fillna(method='ffill', inplace=True)
                    log_to_console(f"Stock data fetched successfully. Price range: ${merged_data['Close'].min():.2f} - ${merged_data['Close'].max():.2f}")
                else:
                    raise ValueError("No stock data returned from Yahoo Finance")
            except Exception as e:
                log_to_console(f"Error fetching stock data: {str(e)}. Skipping price overlay.")
                merged_data['Close'] = 0
        else:
            merged_data['Close'] = 0
            log_to_console("No ticker provided; skipping stock price overlay.")
        
        # Log swap type columns for debugging
        swap_types = [col for col in swap_types if col in merged_data.columns]
        log_to_console(f"Swap type columns after merge: {swap_types}")
        
        # Create bar chart with stock price overlay
        log_to_console(f"Generating bar chart with stock price overlay for {period}...")
        fig, ax1 = plt.subplots(figsize=(12, 6), num=f'{date_label} {period.capitalize()} Volume by Action Type with {ticker or "No"} Price Overlay')
        bar_width = 0.25
        month_years = merged_data['MonthYear']
        index = range(len(month_years))
        
        bars_newt = ax1.bar([i - bar_width for i in index], merged_data['NEWT'], bar_width, label='NEWT', color='blue')
        bars_modi = ax1.bar(index, merged_data['MODI'], bar_width, label='MODI', color='green')
        bars_term = ax1.bar([i + bar_width for i in index], merged_data['TERM'], bar_width, label='TERM', color='red')
        
        ax1.set_xlabel(f'{date_label} ({period.capitalize()})')
        ax1.set_ylabel('Number of Actions', color='black')
        ax1.tick_params(axis='y', labelcolor='black')
        plt.xticks(index, month_years.dt.strftime(date_format), rotation=45 if period == 'daily' else 90)
        ax1.legend(loc='upper left')
        
        if ticker and 'Close' in merged_data.columns and merged_data['Close'].max() > 0:
            ax2 = ax1.twinx()
            trendline, = ax2.plot(index, merged_data['Close'], color='orange', marker='o', linewidth=2, label=f'{ticker} Close Price')
            ax2.set_ylabel(f'{ticker} Closing Price ($)', color='orange')
            ax2.tick_params(axis='y', labelcolor='orange')
            ax2.legend(loc='upper right')
            log_to_console("Stock price line added to secondary axis.")
        else:
            log_to_console("No valid stock price data; skipping overlay.")
        
        plt.title(f'Volume of NEWT, MODI, and TERM Actions by {date_label} {period.capitalize()} with {ticker or "No"} Price Overlay ({os.path.splitext(os.path.basename(csv_file))[0]})')
        plt.tight_layout()
        log_to_console("Bar chart with overlay created successfully.")
        
        # Add hover functionality for both bars and trendline
        log_to_console("Adding hover functionality to chart...")
        try:
            cursor = mplcursors.cursor([bars_newt, bars_modi, bars_term, trendline], hover=True)
            @cursor.connect("add")
            def on_add(sel):
                try:
                    idx = int(sel.index)
                    log_to_console(f"Hover event at index: {idx}")
                    
                    if idx < 0 or idx >= len(merged_data):
                        log_to_console(f"Invalid hover index: {idx}. Skipping tooltip.")
                        sel.annotation.set_text("Invalid index for hover data")
                        return
                    
                    month_year = merged_data['MonthYear'].iloc[idx].strftime(date_format)
                    stock_price = merged_data.get('Close', pd.Series([0] * len(merged_data))).iloc[idx]
                    
                    is_trendline = sel.artist == trendline if ticker and 'Close' in merged_data.columns and merged_data['Close'].max() > 0 else False
                    
                    action_text = []
                    for action in action_types:
                        try:
                            count = merged_data.get(action, pd.Series([0] * len(merged_data))).iloc[idx]
                            notional = merged_data.get(f'{action}_notional', pd.Series([0] * len(merged_data))).iloc[idx]
                            if pd.notna(count) and count > 0:
                                action_text.append(f"{action}: {int(count)} (Notional: ${notional:,.2f})")
                            else:
                                log_to_console(f"Skipping action type '{action}' at index {idx}: count is {count}")
                        except Exception as e:
                            log_to_console(f"Error processing action type '{action}' at index {idx}: {str(e)}")
                    
                    swap_type_text = []
                    for col in swap_types:
                        try:
                            value = merged_data.at[idx, col]
                            if pd.notna(value) and value > 0:
                                swap_type_text.append(f"{col}: {int(value)}")
                            else:
                                log_to_console(f"Skipping swap type column '{col}' at index {idx}: value is {value}")
                        except Exception as e:
                            log_to_console(f"Error processing swap type column '{col}' at index {idx}: {str(e)}")
                    
                    action_text = '\n'.join(action_text) if action_text else 'None'
                    swap_type_text = '\n'.join(swap_type_text) if swap_type_text else 'None'
                    log_to_console(f"Action text for index {idx}: {action_text}")
                    log_to_console(f"Swap type text for index {idx}: {swap_type_text}")
                    
                    if is_trendline:
                        hover_text = f"{date_label} ({period.capitalize()}): {month_year}\n"
                        if stock_price > 0:
                            hover_text += f"{ticker} Close: ${stock_price:,.2f}\n"
                        if action_text != 'None' or swap_type_text != 'None':
                            hover_text += f"Actions:\n{action_text}\n" if action_text != 'None' else ''
                            hover_text += f"Swap Types:\n{swap_type_text}" if swap_type_text != 'None' else ''
                    else:
                        hover_text = f"{date_label} ({period.capitalize()}): {month_year}\n"
                        hover_text += f"Actions:\n{action_text}\n" if action_text != 'None' else ''
                        if ticker and stock_price > 0:
                            hover_text += f"{ticker} Close: ${stock_price:,.2f}\n"
                        hover_text += f"Swap Types:\n{swap_type_text}" if swap_type_text != 'None' else ''
                    
                    sel.annotation.set_text(hover_text)
                    sel.annotation.get_bbox_patch().set_fc('white')
                    sel.annotation.get_bbox_patch().set_alpha(0.8)
                except Exception as e:
                    log_to_console(f"Error in hover callback at index {idx}: {str(e)}")
                    sel.annotation.set_text("Error displaying hover data")
            log_to_console("Hover functionality added.")
        except Exception as e:
            log_to_console(f"Error setting up mplcursors: {str(e)}")
            print("Warning: Hover functionality could not be added due to an error. Chart will still be displayed.")
        
        chart_file = os.path.join(cwd, f'action_volume_{date_label.lower().replace(" ", "_")}_{period}_{"with_" + ticker.lower() if ticker else "no"}_overlay_{os.path.splitext(os.path.basename(csv_file))[0]}.png')
        log_to_console(f"Saving chart to '{chart_file}'...")
        try:
            plt.savefig(chart_file)
            log_to_console("Chart saved successfully.")
        except Exception as e:
            log_to_console(f"Error saving chart: {str(e)}")
            print(f"Warning: Could not save chart to '{chart_file}'. Displaying chart only.")
        
        try:
            plt.show()
            log_to_console("Chart displayed successfully.")
        except Exception as e:
            log_to_console(f"Error displaying chart: {str(e)}")
            print("Error: Could not display chart. Please check the Matplotlib backend configuration.")
    
    elif expiry_type == 'all':
        chart_all_expiries(df_chart, ticker, date_label, period, csv_file, cwd)

# Final note
log_to_console("Script execution completed.")
print("Note: Notional amounts and quantities are calculated for all non-basket swap entries (excluding Equity:Swap:PriceReturnBasicPerformance:Basket) due to unclear weighting information for basket swaps.")
