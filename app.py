"""
IA Market Analyzer — DIAGNÓSTICO
Este script prueba los imports uno a uno para detectar dónde cuelga el arranque.
"""
import sys
print(f"DIAG 1: Python {sys.version}", flush=True)

print("DIAG 2: Importing streamlit...", flush=True)
import streamlit as st
print("DIAG 3: streamlit OK", flush=True)

st.set_page_config(page_title="IA Market Analyzer - Diagnóstico", page_icon="🔍", layout="wide")
print("DIAG 4: page_config set", flush=True)

st.title("🔍 IA Market Analyzer — Diagnóstico de arranque")
st.write(f"Python: `{sys.version}`")

print("DIAG 5: Importing stdlib...", flush=True)
import requests, os, json, hashlib, sqlite3, datetime, time
print("DIAG 6: stdlib OK", flush=True)
st.success("✅ stdlib (requests, os, json, hashlib, sqlite3, datetime, time)")

print("DIAG 7: Importing pandas...", flush=True)
import pandas as pd
print("DIAG 8: pandas OK", flush=True)
st.success(f"✅ pandas {pd.__version__}")

print("DIAG 9: Importing plotly...", flush=True)
import plotly.express as px
import plotly.graph_objects as go
print("DIAG 10: plotly OK", flush=True)
st.success("✅ plotly")

print("DIAG 11: Importing openai...", flush=True)
from openai import OpenAI
import openai
print(f"DIAG 12: openai {openai.__version__} OK", flush=True)
st.success(f"✅ openai {openai.__version__}")

print("DIAG 13: Importing dotenv...", flush=True)
from dotenv import load_dotenv
load_dotenv()
print("DIAG 14: dotenv OK", flush=True)
st.success("✅ dotenv + load_dotenv")

print("DIAG 15: Testing SQLite /tmp...", flush=True)
con = sqlite3.connect("/tmp/diag_test.db")
con.execute("CREATE TABLE IF NOT EXISTS t (x TEXT)")
con.execute("INSERT INTO t VALUES ('ok')")
con.commit()
row = con.execute("SELECT x FROM t").fetchone()
con.close()
print(f"DIAG 16: SQLite /tmp OK: {row}", flush=True)
st.success(f"✅ SQLite /tmp write+read: {row}")

print("DIAG 17: Checking env vars...", flush=True)
has_openai = bool(os.environ.get("OPENAI_API_KEY"))
has_google = bool(os.environ.get("GOOGLE_API_KEY"))
st.info(f"OPENAI_API_KEY present: {has_openai}")
st.info(f"GOOGLE_API_KEY present: {has_google}")
print(f"DIAG 18: env vars checked. OPENAI={has_openai}, GOOGLE={has_google}", flush=True)

st.balloons()
st.title("🎉 ¡Todo OK! La app puede arrancar normalmente.")
print("DIAG 19: Diagnostic complete!", flush=True)
