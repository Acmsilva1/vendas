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
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"

def get_db_connection():
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    creds_dict = json.loads(creds_json)
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open_by_key(SPREADSHEET_ID)

def limpar_valor_blindado(valor):
    """Lógica agressiva para limpar R$, pontos e valores grudados"""
    if pd.isna(valor) or valor == "":
        return 0.0
    
    # Converte para string e remove R$ e espaços
    s = str(valor).replace('R$', '').replace(' ', '').strip()
    
    # Se houver valores grudados (ex: 25,0027,00), tenta pegar apenas o primeiro padrão decimal
    # Isso resolve o erro 'R$ 25,00R$ 27,00' que apareceu no seu log
    match = re.search(r'(\d+[\d\.,]*)', s)
    if match:
        s = match.group(1)
    
    # Ajusta separadores: remove ponto de milhar e troca vírgula decimal por ponto
    # Ex: 1.200,50 -> 1200.50
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'): # Padrão PT-BR 1.000,00
            s = s.replace('.', '').replace(',', '.')
        else: # Padrão EN 1,000.00
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
        
    try:
        return float(s)
    except:
        return 0.0

def processar_dados():
    sh = get_db_connection()
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # Aplicação da limpeza em cada linha (Governança contra dados sujos)
    df_vendas['VALOR DA VENDA'] = df_vendas['VALOR DA VENDA'].apply(limpar_valor_blindado)
    df_gastos['VALOR'] = df_gastos['VALOR'].apply(limpar_valor_blindado)
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje = agora.date()
    inicio_mes = hoje.replace(day=1)

    # Tratamento de datas
    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # KPIs Principais
    v_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()
    g_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]['VALOR'].sum()
    v_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes]['VALOR DA VENDA'].sum()
    g_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]['VALOR'].sum()

    # Ranking de Sabores (Mês)
    ranking_sabores = df_vendas[df_vendas['DATA_DT'] >= inicio_mes].groupby('SABORES').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    # Ranking de Despesas (Mês)
    # Garante que a coluna 'DESCRIÇÃO' exista ou usa a primeira disponível
    col_desc = 'DESCRIÇÃO' if 'DESCRIÇÃO' in df_gastos.columns else df_gastos.columns[0]
    ranking_despesas = df_gastos[df_gastos['DATA_DT'] >= inicio_mes].groupby(col_desc).agg(
        total=('VALOR', 'sum')
    ).reset_index().sort_values(by='total', ascending=False).to_dict(orient='records')
    
    # Padroniza nome da chave para o HTML
    for item in ranking_despesas:
        if col_desc != 'DESCRIÇÃO':
            item['DESCRIÇÃO'] = item.pop(col_desc)

    # Log Últimas 5
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

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    try:
        return processar_dados()
    except Exception as e:
        return {"erro": str(e)}
