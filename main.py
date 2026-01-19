import os
import json
import pandas as pd
import gspread
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import pytz

app = FastAPI()
templates = Jinja2Templates(directory="templates")
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"

def get_db_connection():
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    creds_dict = json.loads(creds_json)
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open_by_key(SPREADSHEET_ID)

def limpar_valor(df, coluna):
    if coluna not in df.columns: return df
    df[coluna] = df[coluna].astype(str).str.extract(r'(\d+[\d\.,]*)')[0].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    df[coluna] = pd.to_numeric(df[coluna], errors='coerce').fillna(0)
    return df

def processar_dados():
    sh = get_db_connection()
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # Limpeza e Datas
    df_vendas = limpar_valor(df_vendas, 'VALOR DA VENDA')
    df_gastos = limpar_valor(df_gastos, 'VALOR')
    
    tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(tz).date()
    inicio_mes = hoje.replace(day=1)

    for df in [df_vendas, df_gastos]:
        df['DATA_DT'] = pd.to_datetime(df['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # --- CÁLCULOS IGUAIS AO STREAMLIT ---
    # Vendas
    vendas_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]
    vendas_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]
    
    total_mes = vendas_mes['VALOR DA VENDA'].sum()
    total_hoje = vendas_hoje['VALOR DA VENDA'].sum()
    ticket_medio = total_mes / len(vendas_mes) if len(vendas_mes) > 0 else 0

    # Gastos
    gastos_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]
    total_gastos_mes = gastos_mes['VALOR'].sum()

    # Top Sabores (Gráfico de Pizza)
    top_sabores = vendas_mes['SABORES'].value_counts().head(5).to_dict()

    return {
        "vendas_hoje": float(total_hoje),
        "vendas_mes": float(total_mes),
        "gastos_mes": float(total_gastos_mes),
        "lucro_mes": float(total_mes - total_gastos_mes),
        "ticket_medio": float(ticket_medio),
        "top_sabores": top_sabores,
        "ultima_atualizacao": datetime.now(tz).strftime("%H:%M:%S")
    }

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    return processar_dados()
