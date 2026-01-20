import os
import json
import pandas as pd
import gspread
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import pytz

app = FastAPI()
templates = Jinja2Templates(directory="templates")
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"

def get_db_connection():
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    creds_dict = json.loads(creds_json)
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open_by_key(SPREADSHEET_ID)

def limpar_valor(df, coluna):
    if coluna not in df.columns: return df
    df[coluna] = df[coluna].astype(str).str.extract(r'(\d+[\d\.,]*)')[0].str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    df[coluna] = pd.to_numeric(df[coluna], errors='coerce').fillna(0)
    return df

def processar_dados():
    sh = get_db_connection()
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    df_vendas = limpar_valor(df_vendas, 'VALOR DA VENDA')
    df_gastos = limpar_valor(df_gastos, 'VALOR')
    
    tz = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(tz)
    hoje = agora.date()
    inicio_mes = hoje.replace(day=1)

    # Tratamento de datas
    df_vendas['DATA_DT'] = pd.to_datetime(df_vendas['DATA E HORA'], dayfirst=True, errors='coerce').dt.date
    df_gastos['DATA_DT'] = pd.to_datetime(df_gastos['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # --- KPIs ANALÍTICOS ---
    vendas_mes = df_vendas[df_vendas['DATA_DT'] >= inicio_mes].copy()
    total_mes = vendas_mes['VALOR DA VENDA'].sum()
    qtd_vendas_mes = len(vendas_mes)
    ticket_medio = total_mes / qtd_vendas_mes if qtd_vendas_mes > 0 else 0

    # Projeção de Faturamento (Governança: Previsibilidade)
    dias_passados = agora.day
    venda_media_diaria = total_mes / dias_passados
    projecao_fim_mes = venda_media_diaria * 30 # Estimativa simples

    # Gastos e Lucro
    gastos_mes = df_gastos[df_gastos['DATA_DT'] >= inicio_mes]
    total_gastos = gastos_mes['VALOR'].sum()

    # --- TABELA 1: RANKING DE SABORES (VALOR E VOLUME) ---
    ranking_sabores = vendas_mes.groupby('SABORES').agg(
        vendas=('VALOR DA VENDA', 'sum'),
        quantidade=('VALOR DA VENDA', 'count')
    ).reset_index().sort_values(by='vendas', ascending=False).to_dict(orient='records')

    # --- TABELA 2: ÚLTIMAS 5 VENDAS ---
    ultimas_vendas = df_vendas.sort_values(by='DATA E HORA', ascending=False).head(5)[['DATA E HORA', 'SABORES', 'VALOR DA VENDA']].to_dict(orient='records')

    return {
        "vendas_hoje": float(df_vendas[df_vendas['DATA_DT'] == hoje]['VALOR DA VENDA'].sum()),
        "vendas_mes": float(total_mes),
        "ticket_medio": float(ticket_medio),
        "projecao_mes": float(projecao_fim_mes),
        "gastos_mes": float(total_gastos),
        "lucro_mes": float(total_mes - total_gastos),
        "ranking_sabores": ranking_sabores,
        "ultimas_vendas": ultimas_vendas,
        "ultima_atualizacao": agora.strftime("%H:%M:%S")
    }

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    return processar_dados()
