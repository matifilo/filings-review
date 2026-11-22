"""Run any SQL query against the database and print the result as a table."""
import sqlite3
import sys

import pandas as pd

con = sqlite3.connect("data/filings.db")
print(pd.read_sql_query(sys.argv[1], con).to_string(index=False))