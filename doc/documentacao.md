Sistema de Gestão Financeira e Dashboard Real-Time
Este projeto implementa uma pipeline completa de Business Intelligence (BI) para controle de vendas e gastos, transformando registros manuais de planilhas em um dashboard analítico automatizado.
+1

🏗️ Arquitetura da Pipeline
A estrutura de dados foi desenhada para garantir a integridade e o histórico das informações:


Ingestão: Os dados são capturados via formulários (Forms) e registrados em uma planilha mestre (Google Sheets).


Processamento (ETL): Script Python hospedado na Render realiza a limpeza de strings financeiras, conversão de tipos (float32) e cálculos agregados via Pandas.


Persistência e Backup: * Todo dia 01 do mês, um script via GitHub Actions move os dados da planilha operacional para um histórico de backup.
+1

O histórico é espelhado para uma tabela em banco de dados Supabase para consultas de longa retenção.
+1


Interface: Dashboard web responsivo construído com FastAPI e JavaScript Vanilla para visualização em tempo real.

🛠️ Stack Técnica
Linguagem: Python 3.x

Framework Web: FastAPI

Manipulação de Dados: Pandas & gspread

Infraestrutura: Render (Hosting) & GitHub Actions (CI/CD / Automação)


Banco de Dados: Google Sheets (Operacional) & Supabase (Histórico) 
+1

🛡️ Governança e Segurança (LGPD)
O projeto foi desenvolvido respeitando as normas de governança e segurança de dados:

Tratamento de Dados: Filtros de sanitização impedem que caracteres inválidos corrompam os cálculos financeiros.

Segurança de Credenciais: Uso estrito de variáveis de ambiente para Service Accounts do GCP e IDs de planilhas, evitando exposição de dados sensíveis.

Consumo de Recursos: Implementação de TTLCache no backend para reduzir o tráfego de rede e evitar sobrecarga nas APIs externas.


Integridade: Processo de backup mensal automatizado para evitar perda de dados operacionais.
+1

📈 Funcionalidades do Dashboard
Indicadores Financeiros: Vendas totais, gastos e lucro previsto (diário e mensal).

Análise de Mix de Produtos: Ranking dos TOP 10 sabores mais vendidos através de processamento de strings (split/explode).

Gestão de Compras: Ranking de insumos mais adquiridos para controle de estoque.

Monitoramento: Exibição das últimas 5 vendas em tempo real para acompanhamento operacional.
