import os
import json
import pandas as pd
import gspread
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
import pytz

app = FastAPI()

# Configuração de templates HTML
templates = Jinja2Templates(directory="templates")

# ID da planilha que você já usa
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"

def get_db_connection():
    """Governança: Acesso seguro via variável de ambiente do Render."""
    creds_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    if not creds_json:
        raise ValueError("ERRO: Variável GCP_SERVICE_ACCOUNT não configurada no Render.")
    
    creds_dict = json.loads(creds_json)
    gc = gspread.service_account_from_dict(creds_dict)
    return gc.open_by_key(SPREADSHEET_ID)

def limpar_coluna_valor(df, coluna_original):
    """Sua lógica original de limpeza robusta para R$, pontos e vírgulas."""
    if coluna_original not in df.columns:
        return df
    
    # Tratando o erro de strings concatenadas (R$ 25,00R$ 27,00) pegando apenas o primeiro valor
    df['Total Limpo'] = (
        df[coluna_original]
        .astype(str)
        .str.extract(r'(\d+[\d\.,]*)')[0] # Pega o primeiro grupo numérico encontrado
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False)
        .str.strip()
    )
    df['Total Limpo'] = pd.to_numeric(df['Total Limpo'], errors='coerce').fillna(0)
    return df

def processar_dados():
    """Lógica de negócio para extrair e calcular KPIs do dia."""
    sh = get_db_connection()
    
    # Extração das abas
    df_vendas = pd.DataFrame(sh.worksheet("vendas").get_all_records())
    df_gastos = pd.DataFrame(sh.worksheet("gastos").get_all_records())

    # Limpeza de valores usando sua lógica
    df_vendas = limpar_coluna_valor(df_vendas, 'VALOR DA VENDA')
    df_gastos = limpar_coluna_valor(df_gastos, 'VALOR')

    # Tratamento de Datas (Fuso de Brasília)
    tz = pytz.timezone('America/Sao_Paulo')
    hoje = datetime.now(tz).date()

    for df in [df_vendas, df_gastos]:
        # Formato %d/%m/%Y %H:%M:%S conforme seu arquivo original
        df['DATA_DT'] = pd.to_datetime(df['DATA E HORA'], dayfirst=True, errors='coerce').dt.date

    # Filtros por 'Hoje'
    vendas_hoje = df_vendas[df_vendas['DATA_DT'] == hoje]
    gastos_hoje = df_gastos[df_gastos['DATA_DT'] == hoje]

    total_vendas = vendas_hoje['Total Limpo'].sum()
    total_gastos = gastos_hoje['Total Limpo'].sum()

    return {
        "vendas_dia": round(float(total_vendas), 2),
        "gastos_dia": round(float(total_gastos), 2),
        "lucro_estimado": round(float(total_vendas - total_gastos), 2),
        "ultima_atualizacao": datetime.now(tz).strftime("%H:%M:%S")
    }

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/status")
async def api_status():
    try:
        return processar_dados()
    except Exception as e:
        return {"erro": str(e)}
