import os
import json
import pandas as pd
import gspread
import gc  # <--- Otimização 3: Garbage Collector
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import pytz
from cachetools import TTLCache

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Cache de 10 min
status_cache = TTLCache(maxsize=1, ttl=600)

_gc_client = None

def get_gc_client():
    global _gc_client
    if _gc_client is None:
        gcp_json = os.environ.get("GCP_SERVICE_ACCOUNT")
        creds_dict = json.loads(gcp_json)
        _gc_client = gspread.service_account_from_dict(creds_dict)
    return _gc_client

def limpar_coluna_financeira(serie):
    return (serie.astype(str)
            .str.replace(r'[R\$\s]', '', regex=True)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
            .str.extract(r'(\d+\.?\d*)')[0]
            .fillna(0)
            .astype('float32')) # <--- Otimização 2: Menos RAM (float32)

def processar_dados():
    if "dashboard_data" in status_cache:
        return status_cache["dashboard_data"]

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    gc_conn = get_gc_client()
    sh = gc_conn.open_by_key(spreadsheet_id)

    # Carga de dados
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # Otimização 2: Tipagem e Categorização para economizar RAM
    df_vendas['VALOR DA VENDA'] = limpar_coluna_financeira(df_vendas['VALOR DA VENDA'])
    df_gastos['VALOR'] = limpar_coluna_financeira(df_gastos['VALOR'])
    
    if 'SABORES' in df_vendas.columns:
        df_vendas['SABORES'] = df_vendas['SABORES'].astype('category')
    
    # Datas e Filtros
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    inicio_mes = agora.date().replace(day=1)

    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # KPIs
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()

    # Ranking e Log
    ranking_sabores = df_vendas.groupby('SABORES', observed=True).agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    ultimas_vendas = df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5).to_dict(orient='records')

    resultado = {
        "vendas_mes": float(v_mes),
        "gastos_mes": float(g_mes),
        "lucro_mes": float(v_mes - g_mes),
        "ranking_sabores": ranking_sabores,
        "ultimas_vendas": ultimas_vendas,
        "ultima_atualizacao": agora.strftime("%H:%M:%S"),
        "ranking_despesas": [] # Adicione sua lógica de despesas aqui se necessário
    }
    
    status_cache["dashboard_data"] = resultado
    
    # Otimização 3: Forçar limpeza de memória após o heavy lifting
    del df_vendas
    del df_gastos
    gc.collect() 
    
    return resultado

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    try:
        return processar_dados()
    except Exception as e:
        return {"erro": str(e)}
