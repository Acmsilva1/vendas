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
    if not creds_json:
        raise ValueError("ERRO: Variável GCP_SERVICE_ACCOUNT não configurada.")
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

    # Limpeza de valores
    df_vendas = limpar_valor(df_vendas, 'VALOR DA VENDA')
    df_gastos = limpar_valor(df_gastos, 'VALOR')
    
    # Datas e Fuso
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje = agora.date()
    inicio_mes = hoje.replace(day=1)

    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # --- MÉTRICAS DASHBOARD ---
    v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()
    g_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()

    # --- RANKING SABORES ---
    ranking_sabores = df_vendas[df_vendas['DATA_DT'] >= inicio_mes].groupby('SABORES').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    # --- RANKING DESPESAS (Para Outliers) ---
    # Usando a coluna 'DESCRIÇÃO' da sua planilha de gastos
    ranking_despesas = df_gastos[df_gastos['DATA_DT'] >= inicio_mes].groupby('DESCRIÇÃO').agg(
        total=('VALOR', 'sum')
    ).reset_index().sort_values(by='total', ascending=False).to_dict(orient='records')

    # --- LOG ÚLTIMAS VENDAS ---
    ultimas_vendas = df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5)[['DATA E HORA', 'SABORES', 'VALOR DA VENDA']].to_dict(orient='records')

    return {
        "vendas_hoje": float(v_hoje),
        "gastos_hoje": float(g_hoje),
        "vendas_mes": float(v_mes),
        "gastos_mes": float(g_mes),
        "lucro_mes": float(v_mes - g_mes),
        "ranking_sabores": ranking_sabores,
        "ranking_despesas": ranking_despesas,
        "ultimas_vendas": ultimas_vendas,
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    try:
        return processar_dados()
    except Exception as e:
        return {"erro": str(e)}
