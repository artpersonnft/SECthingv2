import pandas as pd
import os

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

# Ensure 'Dissemination Identifier' and 'Original Dissemination Identifier' are treated as strings
df['Dissemination Identifier'] = df['Dissemination Identifier'].astype(str)
df['Original Dissemination Identifier'] = df['Original Dissemination Identifier'].astype(str).replace('nan', '')

# Function to trace the chain to its root
def find_root_chain(df, dissem_id, visited=None):
    if visited is None:
        visited = set()
    chain = [dissem_id]
    visited.add(dissem_id)
    
    # Find the row for the current dissemination ID
    row = df[df['Dissemination Identifier'] == dissem_id]
    if row.empty:
        return chain
    
    # Get the original dissemination ID
    orig_id = row['Original Dissemination Identifier'].iloc[0]
    if orig_id and orig_id != '' and orig_id not in visited:
        chain.extend(find_root_chain(df, orig_id, visited))
    
    return chain

# Build chains for all unique dissemination IDs
unique_dissem_ids = df['Dissemination Identifier'].unique()
chains = {}
for dissem_id in unique_dissem_ids:
    chain = find_root_chain(df, dissem_id)
    # The root is the first ID in the chain (or the ID itself if no chain)
    root_id = chain[-1] if len(chain) > 1 else dissem_id
    if root_id not in chains:
        chains[root_id] = []
    chains[root_id].append(dissem_id)

# Identify chains not terminated (no TERM in the chain's final event)
open_chains = []
for root_id, chain_ids in chains.items():
    # Get the latest event in the chain (highest timestamp or last Dissemination ID)
    chain_df = df[df['Dissemination Identifier'].isin(chain_ids)]
    chain_df['Event timestamp'] = pd.to_datetime(chain_df['Event timestamp'])
    latest_event = chain_df.loc[chain_df['Event timestamp'].idxmax()]
    if latest_event['Action type'] != 'TERM':
        open_chains.append({
            'Root ID': root_id,
            'Last Dissemination ID': latest_event['Dissemination Identifier'],
            'Last Action': latest_event['Action type'],
            'Last Timestamp': latest_event['Event timestamp'],
            'Expiration Date': latest_event['Expiration Date'],
            'Swap Type': latest_event['Product name']
        })

# Print open chains
print(f"\nTotal unique position chains: {len(chains)}")
print(f"Open (non-TERM'd) chains: {len(open_chains)}")
print("\nDetails of open chains (not terminated by TERM):")
for chain in open_chains:
    print(f"Root ID: {chain['Root ID']}")
    print(f"Last Dissemination ID: {chain['Last Dissemination ID']}")
    print(f"Last Action: {chain['Last Action']}")
    print(f"Last Timestamp: {chain['Last Timestamp']}")
    print(f"Expiration Date: {chain['Expiration Date']}")
    print(f"Swap Type: {chain['Swap Type']}")
    print("-" * 50)

# Save open chains to a new CSV in the CWD with a name based on the input file
base_name = os.path.splitext(os.path.basename(csv_file))[0]
output_file = os.path.join(cwd, f'open_{base_name}.csv')
open_chains_df = pd.DataFrame(open_chains)
open_chains_df.to_csv(output_file, index=False)
print(f"Open chains saved to '{output_file}' in the current working directory")