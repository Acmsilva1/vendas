import os
import json
import pandas as pd
import gspread
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import pytz
import re

app = FastAPI()
templates = Jinja2Templates(directory="templates")
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"

def get_db_connection():
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    creds_dict = json.loads(creds_json)
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open_by_key(SPREADSHEET_ID)

def limpar_valor_blindado(valor):
    if pd.isna(valor) or valor == "": return 0.0
    s = str(valor).replace('R$', '').replace(' ', '').strip()
    match = re.search(r'(\d+[\d\.,]*)', s)
    if match:
        s = match.group(1)
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s: s = s.replace(',', '.')
    try: return float(s)
    except: return 0.0

def processar_dados():
    sh = get_db_connection()
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    df_vendas['VALOR DA VENDA'] = df_vendas['VALOR DA VENDA'].apply(limpar_valor_blindado)
    df_gastos['VALOR'] = df_gastos['VALOR'].apply(limpar_valor_blindado)
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje, inicio_mes = agora.date(), agora.date().replace(day=1)

    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # Métricas Principais
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()

    # --- RANKING DE DESPESAS (ANÁLISE DE OUTLIERS) ---
    gastos_atuais = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]
    col_desc = 'DESCRIÇÃO' if 'DESCRIÇÃO' in gastos_atuais.columns else gastos_atuais.columns[0]
    
    ranking_despesas = gastos_atuais.groupby(col_desc).agg(
        total=('VALOR', 'sum'),
        frequencia=('VALOR', 'count')
    ).reset_index().sort_values(by='total', ascending=False)

    # Cálculo de Representatividade (Métrica de Governança)
    ranking_despesas['pct'] = (ranking_despesas['total'] / g_mes * 100).round(2) if g_mes > 0 else 0
    
    # Ranking Sabores
    ranking_sabores = df_vendas[df_vendas['DATA_DT'] >= inicio_mes].groupby('SABORES').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False)

    return {
        "vendas_hoje": float(df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()),
        "gastos_hoje": float(df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()),
        "vendas_mes": float(v_mes),
        "gastos_mes": float(g_mes),
        "lucro_mes": float(v_mes - g_mes),
        "ranking_sabores": ranking_sabores.to_dict(orient='records'),
        "ranking_despesas": ranking_despesas.rename(columns={col_desc: 'DESCRIÇÃO'}).to_dict(orient='records'),
        "ultimas_vendas": df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5)[['DATA E HORA', 'SABORES', 'VALOR DA VENDA']].to_dict(orient='records'),
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    try: return processar_dados()
    except Exception as e: return {"erro": str(e)}
