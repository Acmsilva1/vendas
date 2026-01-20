import os
import json
import pandas as pd
import gspread
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
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

    df_vendas = limpar_valor(df_vendas, 'VALOR DA VENDA')
    df_gastos = limpar_valor(df_gastos, 'VALOR')
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje = agora.date()
    inicio_mes = hoje.replace(day=1)

    # Tratamento de datas
    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # --- MÉTRICAS DE HOJE ---
    vendas_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()
    gastos_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()

    # --- MÉTRICAS DO MÊS ---
    vendas_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]
    gastos_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]
    
    total_vendas_mes = vendas_mes['VALOR DA VENDA'].sum()
    total_gastos_mes = gastos_mes['VALOR'].sum()
    lucro_liquido = total_vendas_mes - total_gastos_mes

    # --- TABELAS (MANTIDAS) ---
    ranking_sabores = vendas_mes.groupby('SABORES').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    ultimas_vendas = df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5)[['DATA E HORA', 'SABORES', 'VALOR DA VENDA']].to_dict(orient='records')

    return {
        "vendas_hoje": float(vendas_hoje),
        "gastos_hoje": float(gastos_hoje),
        "vendas_mes": float(total_vendas_mes),
        "gastos_mes": float(total_gastos_mes),
        "lucro_mes": float(lucro_liquido),
        "ranking_sabores": ranking_sabores,
        "ultimas_vendas": ultimas_vendas,
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    return processar_dados()
