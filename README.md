# SECthingv2
This bad boy scrapes every/any type of archive from the SEC in raw form, turning anyone into an archivist. 
It also includes a Python script (analyze.py) to process and visualize swap transaction data from CSV files, featuring dynamic charting with price, volume, and simulated FTD (Failed to Deliver) trends.

Installation:
Install Python 3.12.

From the command line, navigate to the folder containing the script and type: python3 gamecock.py

Usage:
The scraper will auto-install required modules and query for which archives to download.

For analyze.py, install required modules: pip3 install pandas matplotlib mplcursors yfinance
then run python3 analyze.py. Select a subdirectory and CSV file, then choose charting options (e.g., date type, aggregation, ticker) to visualize data.

Note: Post-download functionality is still rough, but AI can help analyze filings. Explore, poke around, and look things up. Make learning great again! :)



