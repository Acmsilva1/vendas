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

# Configuração para renderizar o HTML
templates = Jinja2Templates(directory="templates")

# --- CONFIGURAÇÕES DA PLANILHA ---
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"

def get_db_connection():
    # Governança: Lendo o JSON secreto da variável de ambiente do Render
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    if not creds_json:
        raise ValueError("ERRO: Variável GCP_SERVICE_ACCOUNT não configurada no Render.")
    
    creds_dict = json.loads(creds_json)
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open_by_key(SPREADSHEET_ID)

def processar_dados():
    sh = get_db_connection()
    
    # Extraindo dados (Suas abas)
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # --- SUA LÓGICA DE LIMPEZA (Adaptada do seu código anterior) ---
    for df in [df_vendas, df_gastos]:
        df['DATA E HORA'] = pd.to_datetime(df['DATA E HORA'], dayfirst=True, errors='coerce')

    tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(tz).date()

    # Exemplo de KPIs que você já calculava
    vendas_hoje = df_vendas[df_vendas['DATA E HORA'].dt.date == hoje]
    total_vendas_dia = vendas_hoje['VALOR DA VENDA'].sum()
    
    gastos_hoje = df_gastos[df_gastos['DATA E HORA'].dt.date == hoje]
    total_gastos_dia = gastos_hoje['VALOR'].sum()

    return {
        "vendas_dia": float(total_vendas_dia),
        "gastos_dia": float(total_gastos_dia),
        "lucro_estimado": float(total_vendas_dia - total_gastos_dia),
        "ultima_atualizacao": datetime.now(tz).strftime("%H:%M:%S")
    }

# --- ROTAS DA API ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Rota que entrega a página do Dashboard
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    # Rota que o JavaScript vai consultar a cada X segundos
    try:
        dados = processar_dados()
        return dados
    except Exception as e:
        return {"erro": str(e)}
