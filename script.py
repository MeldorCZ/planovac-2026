import streamlit as st
import pandas as pd
import gspread
import json
from google.oauth2.service_account import Credentials
from datetime import datetime

MONTHS = ["Leden","Únor","Březen","Duben","Květen","Červen",
          "Červenec","Srpen","Září","Říjen","Listopad","Prosinec"]

PEOPLE = ["Vágner", "Vašák", "Tomeček", "Tichý", "Štod"]
DRIVERS = {"Vágner", "Tomeček", "Tichý"}

COLUMNS = [
    "Datum","Den","Víkend","Práce","Lokace","Sklad","Vozidlo",
    "Vágner","Vašák","Tomeček","Tichý","Štod",
    "Start","Konec","Přesčas (h)","Poznámky","Blokace Vágner","Řidič kontrola"
]

def compute_driver_status(row) -> str:
    veh = (row.get("Vozidlo") or "")
    if veh.strip() == "" or veh == "Žádné":
        return ""
    for d in DRIVERS:
        if bool(row.get(d, False)):
            return "OK"
    return "CHYBÍ ŘIDIČ"

def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT_JSON"].strip())
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def sheet_to_df(ws):
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(columns=COLUMNS)

    header = values[0]
    rows = values[1:]

    df = pd.DataFrame(rows, columns=header)

    # zajisti pořadí a existenci sloupců
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[COLUMNS]

    # Datum
    df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce").dt.date

    # checkboxy: "✓" -> bool
    for p in PEOPLE:
        df[p] = df[p].astype(str).str.strip().eq("✓")

    return df

def df_to_sheet(ws, df: pd.DataFrame):
    df = df.copy()

    # bool -> "✓"
    for p in PEOPLE:
        df[p] = df[p].apply(lambda x: "✓" if bool(x) else "")

    # Datum zpět na string
    df["Datum"] = df["Datum"].apply(
        lambda d: d.strftime("%d.%m.%Y") if pd.notnull(d) and d != "" else ""
    )

    # přepočet řidiče (text)
    df["Řidič kontrola"] = df.apply(compute_driver_status, axis=1)

    # zápis: nejdřív header + data
    data = [COLUMNS] + df[COLUMNS].astype(str).values.tolist()
    ws.clear()
    ws.update(data)

st.set_page_config(page_title="Plánovač směn 2026", layout="wide")
st.title("Plánovač směn 2026")

# Volitelné: PIN ochrana
if "APP_PIN" in st.secrets:
    pin = st.text_input("PIN", type="password")
    if pin != st.secrets["APP_PIN"]:
        st.stop()

SHEET_ID = st.secrets["SHEET_ID"]

gc = get_gspread_client()
sh = gc.open_by_key(SHEET_ID)

month = st.selectbox("Vyber měsíc", MONTHS)
ws = sh.worksheet(month)

df = sheet_to_df(ws)

# Editor
col_config = {
    "Práce": st.column_config.SelectboxColumn(
        "Práce",
        options=["", "dovoz", "údržba", "Akce (TiC)", "Akce (externí)"]
    ),
    "Vozidlo": st.column_config.SelectboxColumn(
        "Vozidlo",
        options=["", "Dodávka", "Osobní auto", "Žádné"]
    ),
}

for p in PEOPLE:
    col_config[p] = st.column_config.CheckboxColumn(p)

disabled_cols = ["Den", "Víkend", "Přesčas (h)", "Blokace Vágner", "Řidič kontrola"]

edited = st.data_editor(
    df,
    use_container_width=True,
    num_rows="dynamic",
    column_config=col_config,
    disabled=disabled_cols,
    hide_index=True
)

edited = edited.copy()
edited["Řidič kontrola"] = edited.apply(compute_driver_status, axis=1)

if st.button("Uložit do Google Sheets"):
    df_to_sheet(ws, edited)
    st.success("Uloženo ✅")
