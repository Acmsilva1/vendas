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

# --- CONFIGURAÇÃO VIA VARIÁVEIS DE AMBIENTE (GOVERNANÇA) ---
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GCP_JSON = os.environ.get("GCP_SERVICE_ACCOUNT")

def get_db_connection():
    if not SPREADSHEET_ID or not GCP_JSON:
        raise ValueError("ERRO: Variáveis de ambiente SPREADSHEET_ID ou GCP_SERVICE_ACCOUNT não configuradas!")
    
    creds_dict = json.loads(GCP_JSON)
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open_by_key(SPREADSHEET_ID)

def limpar_valor_blindado(valor):
    """Extrai apenas números de strings sujas como 'R$ 25,00R$ 27,00'"""
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

    # Sanitização de Valores e Strings
    df_vendas['VALOR DA VENDA'] = df_vendas['VALOR DA VENDA'].apply(limpar_valor_blindado)
    df_gastos['VALOR'] = df_gastos['VALOR'].apply(limpar_valor_blindado)
    
    # Tratamento da Coluna PRODUTO (Maiúsculas e sem espaços)
    if 'PRODUTO' in df_gastos.columns:
        df_gastos['PRODUTO'] = df_gastos['PRODUTO'].astype(str).str.upper().str.strip()
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje, inicio_mes = agora.date(), agora.date().replace(day=1)

    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # KPIs dos Cards
    v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()
    g_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()

    # Ranking Sabores (Mês)
    ranking_sabores = df_vendas[df_vendas['DATA_DT'] >= inicio_mes].groupby('SABORES').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    # --- ANÁLISE DE OUTLIERS DE GASTOS (POR PRODUTO) ---
    ranking_despesas = []
    if 'PRODUTO' in df_gastos.columns:
        gastos_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes].copy()
        ranking_despesas = gastos_mes.groupby('PRODUTO').agg(
            total=('VALOR', 'sum')
        ).reset_index().sort_values(by='total', ascending=False)
        
        # Métrica de Representatividade (%)
        ranking_despesas['pct'] = (ranking_despesas['total'] / g_mes * 100).round(2) if g_mes > 0 else 0
        ranking_despesas = ranking_despesas.rename(columns={'PRODUTO': 'DESCRIÇÃO'}).to_dict(orient='records')

    # Log das Últimas 5 Vendas
    ultimas_vendas = df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5)[['DATA E HORA', 'SABORES', 'VALOR DA VENDA']].to_dict(orient='records')

    return {
        "vendas_hoje": float(v_hoje), "gastos_hoje": float(g_hoje),
        "vendas_mes": float(v_mes), "gastos_mes": float(g_mes),
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
    try: return processar_dados()
    except Exception as e: return {"erro": str(e)}
