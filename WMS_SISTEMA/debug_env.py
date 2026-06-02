#!/usr/bin/env python
import os
from dotenv import load_dotenv

load_dotenv('.env')

print(f"WMS_MDB_PATH_PROD: {os.environ.get('WMS_MDB_PATH_PROD')}")
print(f"WMS_MDB_PATH_TEST: {os.environ.get('WMS_MDB_PATH_TEST')}")

import db_mdb
print(f"\nDB_PATH: {db_mdb.DB_PATH}")
print(f"DB_PATH_TEST: {db_mdb.DB_PATH_TEST}")
