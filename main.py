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
from cachetools import TTLCache

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Cache de 10 minutos para não estourar cota do Google nem paciência do usuário
# maxsize=1 pois só guardamos um dicionário de resultados
status_cache = TTLCache(maxsize=1, ttl=600)

# --- SINGLETON PARA CONEXÃO (GOVERNANÇA E PERFORMANCE) ---
_gc_client = None

def get_gc_client():
    global _gc_client
    if _gc_client is None:
        gcp_json = os.environ.get("GCP_SERVICE_ACCOUNT")
        if not gcp_json:
            raise ValueError("GCP_SERVICE_ACCOUNT não configurada!")
        creds_dict = json.loads(gcp_json)
        _gc_client = gspread.service_account_from_dict(creds_dict)
    return _gc_client

def limpar_coluna_financeira(serie):
    """Limpa a coluna inteira de uma vez (Vetorizado) em vez de linha por linha"""
    return (serie.astype(str)
            .str.replace(r'[R\$\s]', '', regex=True)
            .str.replace('.', '', regex=False)
            .str.replace(',', '.', regex=False)
            .str.extract(r'(\d+\.?\d*)')[0]
            .fillna(0)
            .astype(float))

def processar_dados():
    # Se estiver no cache, retorna imediatamente
    if "dashboard_data" in status_cache:
        return status_cache["dashboard_data"]

    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    gc = get_gc_client()
    sh = gc.open_by_key(spreadsheet_id)

    # Pegando tudo de uma vez para reduzir I/O
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # Sanitização Vetorizada (MUITO mais rápido que .apply)
    df_vendas['VALOR DA VENDA'] = limpar_coluna_financeira(df_vendas['VALOR DA VENDA'])
    df_gastos['VALOR'] = limpar_coluna_financeira(df_gastos['VALOR'])
    
    if 'PRODUTO' in df_gastos.columns:
        df_gastos['PRODUTO'] = df_gastos['PRODUTO'].astype(str).str.upper().str.strip()

    # Datas
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje = agora.date()
    inicio_mes = hoje.replace(day=1)

    # Conversão de data otimizada
    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # Como você disse que os dados zeram no mês, o filtro de mês aqui 
    # serve como uma segurança extra de governança
    mask_vendas_mes = df_vendas['DATA_DT'] >= inicio_mes
    mask_gastos_mes = df_gastos['DATA_DT'] >= inicio_mes

    v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()
    g_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()
    
    v_mes = df_vendas[mask_vendas_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[mask_gastos_mes]['VALOR'].sum()

    # Ranking Sabores (Mês)
    ranking_sabores = df_vendas[mask_vendas_mes].groupby('SABORES').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    # Ranking Despesas
    ranking_despesas = []
    if 'PRODUTO' in df_gastos.columns:
        df_g_mes = df_gastos[mask_gastos_mes]
        ranking_despesas = df_g_mes.groupby('PRODUTO').agg(total=('VALOR', 'sum')).reset_index()
        ranking_despesas['pct'] = (ranking_despesas['total'] / g_mes * 100).round(2) if g_mes > 0 else 0
        ranking_despesas = ranking_despesas.rename(columns={'PRODUTO': 'DESCRIÇÃO'}).sort_values(by='total', ascending=False).to_dict(orient='records')

    # Log (Últimas 5)
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
