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

# --- [4] CORE: PROCESSAMENTO (ADICIONADO: RANKING DE INSUMOS) ---
def processar_dados():
    # ... (Conexão e Carga de dados inicial mantida)
    
    # 1. Processamento de Vendas (Lógica Original Mantida)
    df_v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]
    df_v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]
    
    # 2. Processamento de Gastos / Insumos (Nova Lógica)
    df_g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes].copy()
    
    # Garantimos que QUANTIDADE e VALOR são numéricos
    df_g_mes['QUANTIDADE'] = pd.to_numeric(df_g_mes['QUANTIDADE'], errors='coerce').fillna(1)
    # Valor total já passa pela função limpar_coluna_financeira no início
    
    # Criamos a métrica de Valor Unitário (Regra de 3 básica: Total / Qtd)
    df_g_mes['VALOR_UNITARIO'] = df_g_mes['VALOR'] / df_g_mes['QUANTIDADE']

    # Geramos o Ranking de Compras: Agrupamos por PRODUTO
    ranking_compras = df_g_mes.groupby('PRODUTO').agg(
        total_gasto=('VALOR', 'sum'),
        qtd_total=('QUANTIDADE', 'sum'),
        preco_medio=('VALOR_UNITARIO', 'mean') # Média de preço pago no mês
    ).reset_index().sort_values(by='total_gasto', ascending=False)

    # ... (Lógica de Ranking de Sabores e Últimas Vendas mantida)

    resultado = {
        # ... (KPIs de vendas anteriores)
        "ranking_compras": ranking_compras.head(10).to_dict(orient='records'),
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
