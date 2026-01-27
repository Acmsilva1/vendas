"""
SISTEMA DE GESTÃO FINANCEIRA - BACKEND
[RESTAURADO] Versão funcional original.
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

# --- [2] GERENCIAMENTO DE CREDENCIAIS (SINGLETON) ---
def get_gc_client():
    global _gc_client
    if _gc_client is None:
        gcp_json = os.environ.get("GCP_SERVICE_ACCOUNT")
        creds_dict = json.loads(gcp_json)
        _gc_client = gspread.service_account_from_dict(creds_dict)
    return _gc_client

# --- [3] SANITIZAÇÃO DE DADOS FINANCEIROS ---
def limpar_coluna_financeira(serie):
    return (serie.astype(str)
            .str.replace(r'[R\$\s]', '', regex=True)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
            .str.extract(r'(\d+\.?\d*)')[0]
            .fillna(0)
            .astype('float32'))

# --- [4] CORE: PROCESSAMENTO (RANKING DE INSUMOS + ÚLTIMAS VENDAS) ---
# --- [DENTRO DA FUNÇÃO processar_dados] ---

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

    # --- PROCESSAMENTO GASTOS ---
    df_g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes].copy()
    df_g_hoje = df_gastos[df_gastos['DATA_DT'] == hoje] # <--- AQUI: Filtro de hoje

    # --- PROCESSAMENTO VENDAS ---
    df_v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]
    df_v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]
    
    # ... (mantenha os rankings de sabores e insumos como estão no seu código original)

    resultado = {
        "vendas_hoje": float(df_v_hoje['VALOR DA VENDA'].sum()),
        "itens_hoje": int(df_v_hoje.shape[0]),
        
        "gastos_hoje": float(df_g_hoje['VALOR'].sum()), # <--- AQUI: Chave necessária para o index.html
        "itens_gastos_hoje": int(df_g_hoje.shape[0]),   # <--- AQUI: Chave necessária para o index.html
        
        "vendas_mes": float(df_v_mes['VALOR DA VENDA'].sum()), 
        "itens_mes": int(df_v_mes.shape[0]), # <--- AQUI: Corrigindo o undefined de itens no mês
        "gastos_mes": float(df_g_mes['VALOR'].sum()),
        "lucro_mes": float(df_v_mes['VALOR DA VENDA'].sum() - df_g_mes['VALOR'].sum()),
        
        "ranking_sabores": ranking_sabores if 'ranking_sabores' in locals() else [],
        "ultimas_vendas": ultimas_5 if 'ultimas_5' in locals() else [],
        "ranking_compras": ranking_compras if 'ranking_compras' in locals() else [],
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }
    
    status_cache["dashboard_data"] = resultado
    gc.collect() 
    return resultado
    
# --- [5] ENDPOINT DE API (STATUS) ---
@app.get("/api/status")
async def api_status():
    try: return processar_dados()
    except Exception as e: return {"erro": str(e)}

# --- [6] RENDERIZAÇÃO DA INTERFACE (HOME) ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
