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

# --- [4] CORE: PROCESSAMENTO (COM EXPLOSÃO DE ITENS CORRETA) ---
def processar_dados():
    if "dashboard_data" in status_cache:
        return status_cache["dashboard_data"]

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    sh = get_gc_client().open_by_key(spreadsheet_id)

    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # [3] Sanitização
    df_vendas['VALOR DA VENDA'] = limpar_coluna_financeira(df_vendas['VALOR DA VENDA'])
    df_gastos['VALOR'] = limpar_coluna_financeira(df_gastos['VALOR'])
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje, inicio_mes = agora.date(), agora.date().replace(day=1)

    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # --- REINTEGRAÇÃO DA FUNÇÃO DE CONTAGEM ---
    def contar_itens(df_subset):
        """Conta individualmente cada sabor separado por vírgula."""
        if df_subset.empty: return 0
        return df_subset['SABORES'].astype(str).str.split(',').explode().str.strip().shape[0]

    df_v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]
    df_v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]
    
    # KPIs usando a contagem real de produtos
    vendas_hoje_valor = float(df_v_hoje['VALOR DA VENDA'].sum())
    itens_hoje_real = int(contar_itens(df_v_hoje)) # <--- Aplicando a função
    
    vendas_mes_valor = float(df_v_mes['VALOR DA VENDA'].sum())
    itens_mes_real = int(contar_itens(df_v_mes)) # <--- Aplicando a função

    # Lógica das Últimas 5 Vendas (Adicionada conforme pedido anterior)
    ultimas_5 = df_v_hoje.tail(5).sort_values(by='DATA E HORA', ascending=False).to_dict(orient='records')

    # Ranking Sabores Original (Mantido)
    df_exploded = df_v_mes.copy()
    df_exploded['SABORES_SPLIT'] = df_exploded['SABORES'].astype(str).str.split(',')
    df_exploded = df_exploded.explode('SABORES_SPLIT')
    df_exploded['SABORES_SPLIT'] = df_exploded['SABORES_SPLIT'].str.strip().str.upper()

    ranking_sabores = df_exploded.groupby('SABORES_SPLIT').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('SABORES_SPLIT', 'count')
    ).reset_index().rename(columns={'SABORES_SPLIT': 'SABORES'}).sort_values(by='quantidade', ascending=False).to_dict(orient='records')

    resultado = {
        "vendas_hoje": vendas_hoje_valor,
        "itens_hoje": itens_hoje_real,
        "vendas_mes": vendas_mes_valor, 
        "itens_mes": itens_mes_real,
        "gastos_mes": float(df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()),
        "lucro_mes": float(vendas_mes_valor - df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()),
        "ranking_sabores": ranking_sabores[:10],
        "ultimas_vendas": ultimas_5,
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
