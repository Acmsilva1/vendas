📊 Dashboard Financeiro Inteligente: Gestão IA & Dados
Este projeto implementa uma pipeline de dados ponta a ponta (End-to-End), transformando registros brutos de operações diárias em um dashboard analítico de alta performance. A solução foca na visibilidade do lucro real e na automação do ciclo de vida dos dados financeiros.
+2

🏗️ Arquitetura da Pipeline
O sistema foi desenhado seguindo princípios de engenharia de dados moderna, dividido em camadas principais:


Camada de Ingestão: Captura de dados via Google Forms para garantir uma interface de entrada padronizada e amigável.

Camada de Processamento (ETL): Engine em Python (FastAPI) que realiza a limpeza de strings, tratamento de nulos e conversão de tipos financeiros com alta precisão.


Camada de Armazenamento & Backup: Automação via GitHub Actions que realiza o snapshot mensal dos dados operacionais para o "Histórico de Vendas" e sincroniza com banco de dados Supabase.
+1

Camada de Entrega: Frontend responsivo que consome uma API otimizada com cache inteligente para garantir carregamento instantâneo.

🛠️ Tecnologias Utilizadas
Linguagem: Python 3.10+.

Análise de Dados: Pandas, gspread, Regex.

Web Framework: FastAPI, Jinja2, Uvicorn.


Infraestrutura: Render (Hospedagem), GitHub Actions (Automação de Backup).
+1


Bancos de Dados: Google Sheets API e Supabase (PostgreSQL).
+1

🛡️ Governança e Melhores Práticas
Este projeto aplica normas de governança e segurança de dados essenciais para ambientes corporativos:

Segurança (LGPD): Sanitização rigorosa de inputs e isolamento total de credenciais através de variáveis de ambiente (os arquivos contêm verificação de dados sensíveis antes do processamento).

Otimização de Recursos: Uso de TTLCache para evitar o "throttling" de APIs e gestão de memória com gc.collect() para performance em ambientes cloud limitados.

Integridade de Dados: Processamento de strings financeiras complexas (R$ -> Float32) para evitar erros de arredondamento em cálculos de lucro.

🚀 Funcionalidades Chave
Visão Geral: Monitoramento de faturamento, gastos e lucro previsto em tempo real.

Inteligência de Vendas: Ranking automático de sabores com base no desmembramento de pedidos múltiplos.

Gestão de Insumos: Identificação dos maiores centros de custo no mês para otimização de compras.

Timeline Operacional: Histórico imediato das últimas 5 vendas realizadas hoje para conferência rápida.
