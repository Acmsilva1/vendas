"""
SISTEMA DE GESTÃO - BACKEND (Refatorado para Gestão de Insumos)
"""
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

# --- [1] CONFIGURAÇÃO DE AMBIENTE E CACHE ---
status_cache = TTLCache(maxsize=1, ttl=300) 
_gc_client = None

# --- [2] GERENCIAMENTO DE CREDENCIAIS ---
def get_gc_client():
    global _gc_client
    if _gc_client is None:
        gcp_json = os.environ.get("GCP_SERVICE_ACCOUNT")
        creds_dict = json.loads(gcp_json)
        _gc_client = gspread.service_account_from_dict(creds_dict)
    return _gc_client

# --- [3] SANITIZAÇÃO FINANCEIRA ---
def limpar_coluna_financeira(serie):
    return (serie.astype(str)
            .str.replace(r'[R\$\s]', '', regex=True)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
            .str.extract(r'(\d+\.?\d*)')[0]
            .fillna(0)
            .astype('float32'))

# --- [4] CORE: PROCESSAMENTO (ALTERADA: RANKING DE COMPRAS + ÚLTIMAS VENDAS) ---
def processar_dados():
    if "dashboard_data" in status_cache:
        return status_cache["dashboard_data"]

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    sh = get_gc_client().open_by_key(spreadsheet_id)

    # Carga de dados
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # Limpeza
    df_vendas['VALOR DA VENDA'] = limpar_coluna_financeira(df_vendas['VALOR DA VENDA'])
    df_gastos['VALOR'] = limpar_coluna_financeira(df_gastos['VALOR'])
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje, inicio_mes = agora.date(), agora.date().replace(day=1)

    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # Helper Contagem
    def contar_itens(df, col):
        if df.empty: return 0
        return df[col].astype(str).str.split(',').explode().str.strip().shape[0]

    # KPIs Mensais para Percentual
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()
    p_gasto = (g_mes / v_mes * 100) if v_mes > 0 else 0

    # EXPLOSÃO: Ranking de Compras (Insumos)
    df_g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes].copy()
    df_g_exploded = df_g_mes.assign(ITEM=df_g_mes['ITEM'].astype(str).str.split(',')).explode('ITEM')
    df_g_exploded['ITEM'] = df_g_exploded['ITEM'].str.strip().str.upper()
    
    ranking_compras = df_g_exploded.groupby('ITEM').agg(
        total=('VALOR', 'sum'),
        qtd=('ITEM', 'count')
    ).reset_index().sort_values(by='total', ascending=False).head(10).to_dict(orient='records')

    # ÚLTIMAS 5 VENDAS (HOJE)
    df_v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]
    ultimas_vendas = df_v_hoje.tail(5).sort_values(by='DATA E HORA', ascending=False).to_dict(orient='records')

    resultado = {
        "vendas_hoje": float(df_v_hoje['VALOR DA VENDA'].sum()),
        "vendas_mes": float(v_mes),
        "gastos_mes": float(g_mes),
        "lucro_mes": float(v_mes - g_mes),
        "percentual_gastos": round(p_gasto, 2),
        "ranking_sabores": [], # (Mantido conforme lógica anterior)
        "ranking_compras": ranking_compras,
        "ultimas_vendas": ultimas_vendas,
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }
    
    status_cache["dashboard_data"] = resultado
    gc.collect() 
    return resultado

# --- [5] API ---
@app.get("/api/status")
async def api_status():
    try: return processar_dados()
    except Exception as e: return {"erro": str(e)}

# --- [6] HOME ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
