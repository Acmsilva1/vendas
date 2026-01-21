import os
import json
import pandas as pd
import gspread
import gc
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import pytz
from cachetools import TTLCache

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Cache de 10 min: Protege a cota do Google e a RAM do Render
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
    """Limpeza vetorizada para performance máxima"""
    return (serie.astype(str)
            .str.replace(r'[R\$\s]', '', regex=True)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
            .str.extract(r'(\d+\.?\d*)')[0]
            .fillna(0)
            .astype('float32'))

def processar_dados():
    if "dashboard_data" in status_cache:
        return status_cache["dashboard_data"]

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    gc_conn = get_gc_client()
    sh = gc_conn.open_by_key(spreadsheet_id)

    # Carga de dados (Vendas e Gastos)
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # Sanitização e Otimização de Tipos
    df_vendas['VALOR DA VENDA'] = limpar_coluna_financeira(df_vendas['VALOR DA VENDA'])
    df_gastos['VALOR'] = limpar_coluna_financeira(df_gastos['VALOR'])
    
    if 'SABORES' in df_vendas.columns:
        df_vendas['SABORES'] = df_vendas['SABORES'].astype('category')
    if 'PRODUTO' in df_gastos.columns:
        df_gastos['PRODUTO'] = df_gastos['PRODUTO'].astype(str).str.upper().str.strip()
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje, inicio_mes = agora.date(), agora.date().replace(day=1)

    # Conversão de datas
    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # --- KPIs Consolidados ---
    v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()
    g_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()
    
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()

    # Ranking Sabores
    ranking_sabores = df_vendas[df_vendas['DATA_DT'] >= inicio_mes].groupby('SABORES', observed=True).agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    # Ranking Despesas com Outliers
    ranking_despesas = []
    if 'PRODUTO' in df_gastos.columns:
        df_g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]
        ranking_despesas = df_g_mes.groupby('PRODUTO').agg(total=('VALOR', 'sum')).reset_index()
        ranking_despesas['pct'] = (ranking_despesas['total'] / g_mes * 100).round(2) if g_mes > 0 else 0
        ranking_despesas = ranking_despesas.rename(columns={'PRODUTO': 'DESCRIÇÃO'}).sort_values(by='total', ascending=False).to_dict(orient='records')

    # Últimos Lançamentos
    ultimas_vendas = df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5)[['DATA E HORA', 'SABORES', 'VALOR DA VENDA']].to_dict(orient='records')

    resultado = {
        "vendas_hoje": float(v_hoje), "gastos_hoje": float(g_hoje),
        "vendas_mes": float(v_mes), "gastos_mes": float(g_mes),
        "lucro_mes": float(v_mes - g_mes),
        "ranking_sabores": ranking_sabores,
        "ranking_despesas": ranking_despesas,
        "ultimas_vendas": ultimas_vendas,
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }
    
    status_cache["dashboard_data"] = resultado
    del df_vendas, df_gastos
    gc.collect() 
    return resultado

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    try: return processar_dados()
    except Exception as e: return {"erro": str(e)}
