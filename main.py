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
            .astype('float32'))

def processar_dados():
    if "dashboard_data" in status_cache:
        return status_cache["dashboard_data"]

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    sh = get_gc_client().open_by_key(spreadsheet_id)

    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    df_vendas['VALOR DA VENDA'] = limpar_coluna_financeira(df_vendas['VALOR DA VENDA'])
    df_gastos['VALOR'] = limpar_coluna_financeira(df_gastos['VALOR'])
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje, inicio_mes = agora.date(), agora.date().replace(day=1)

    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # --- KPI: Vendas e Itens de Hoje ---
    df_v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje].copy()
    v_hoje = df_v_hoje['VALOR DA VENDA'].sum()
    # Explodimos os sabores de hoje para contar itens reais
    df_v_hoje['S_SPLIT'] = df_v_hoje['SABORES'].astype(str).str.split(',')
    itens_hoje = df_v_hoje.explode('S_SPLIT').shape[0] if not df_v_hoje.empty else 0

    # --- KPIs Consolidados ---
    g_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()

    # --- Lógica de Explosão de Sabores (Mês) ---
    df_v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes].copy()
    df_v_mes['SABORES_SPLIT'] = df_v_mes['SABORES'].astype(str).str.split(',')
    df_exploded = df_v_mes.explode('SABORES_SPLIT')
    df_exploded['SABORES_SPLIT'] = df_exploded['SABORES_SPLIT'].str.strip().str.upper()

    # Valor Proporcional para não duplicar faturamento no ranking
    df_exploded['ITENS_NA_LINHA'] = df_exploded.groupby(level=0)['SABORES_SPLIT'].transform('count')
    df_exploded['VALOR_PROPORCIONAL'] = df_exploded['VALOR DA VENDA'] / df_exploded['ITENS_NA_LINHA']

    ranking_sabores = df_exploded.groupby('SABORES_SPLIT').agg(
        vendas=('VALOR_PROPORCIONAL', 'sum'),
        quantidade=('SABORES_SPLIT', 'count')
    ).reset_index().rename(columns={'SABORES_SPLIT': 'SABORES'}).sort_values(by='quantidade', ascending=False).to_dict(orient='records')

    # Ranking Despesas
    ranking_despesas = []
    if 'PRODUTO' in df_gastos.columns:
        df_g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]
        ranking_despesas = df_g_mes.groupby('PRODUTO').agg(total=('VALOR', 'sum')).reset_index()
        ranking_despesas['pct'] = (ranking_despesas['total'] / g_mes * 100).round(2) if g_mes > 0 else 0
        ranking_despesas = ranking_despesas.rename(columns={'PRODUTO': 'DESCRIÇÃO'}).sort_values(by='total', ascending=False).to_dict(orient='records')

    ultimas_vendas = df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5).to_dict(orient='records')

    resultado = {
        "vendas_hoje": float(v_hoje),
        "itens_hoje": int(itens_hoje),
        "gastos_hoje": float(g_hoje),
        "vendas_mes": float(v_mes), 
        "gastos_mes": float(g_mes),
        "lucro_mes": float(v_mes - g_mes),
        "ranking_sabores": ranking_sabores,
        "ranking_despesas": ranking_despesas,
        "ultimas_vendas": ultimas_vendas,
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }
    
    status_cache["dashboard_data"] = resultado
    del df_vendas, df_gastos, df_exploded
    gc.collect() 
    return resultado

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    try: return processar_dados()
    except Exception as e: return {"erro": str(e)}
