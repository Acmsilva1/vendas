Dashboard Financeiro e Pipeline de Dados: Gestão IA & Dados
Este projeto implementa uma solução completa de engenharia e visualização de dados para gestão financeira. Ele automatiza o ciclo de vida do dado, desde a coleta operacional até a geração de insights estratégicos em tempo real, eliminando processos manuais e erros de cálculo.

Arquitetura da Solução
O ecossistema foi estruturado para ser resiliente e escalável, dividindo-se em camadas:

Ingestão e Registro: Os dados são inseridos via Google Forms, alimentando planilhas que servem como interface de entrada amigável para a operação diária.

Motor de ETL (Python): O backend, desenvolvido em FastAPI, atua como a inteligência central. Ele extrai os dados brutos, realiza a limpeza de caracteres financeiros, trata inconsistências e aplica transformações complexas, como o desmembramento de vendas múltiplas (explode) para análise individual de produtos.

Ciclo de Backup e Histórico: Para garantir a segurança e a performance, um fluxo automatizado via GitHub Actions transfere os dados operacionais para um histórico mensal e para um banco de dados Supabase (PostgreSQL) todo dia primeiro de cada mês.

Camada de Visualização: Um dashboard responsivo que consome uma API otimizada com sistema de cache, garantindo que as informações de lucro, ranking de insumos e performance de vendas estejam sempre disponíveis sem sobrecarregar as fontes de dados.

Diferenciais Técnicos e Governança
Eficiência de Memória: O sistema utiliza tipagem otimizada (float32) e coleta de lixo manual para operar com alto desempenho em ambientes de nuvem com recursos limitados.

Segurança de Dados: Implementação rigorosa de variáveis de ambiente para proteção de credenciais de serviço, garantindo que chaves de API e informações sensíveis nunca fiquem expostas.

Integridade Financeira: Algoritmos de sanitização via Regex garantem que variações na digitação de valores monetários não corrompam os indicadores de lucro e faturamento.

Disponibilidade: Uso de cache com tempo de vida (TTL) para equilibrar a atualização dos dados em tempo real com as cotas de requisição das APIs externas.

Funcionalidades Principais
Monitoramento em tempo real de vendas e gastos diários vs. mensais.

Cálculo automático de lucro líquido previsto.

Ranking de sabores mais vendidos com métricas de quantidade e faturamento.

Análise de curva de gastos por insumo para otimização de compras.

Log das últimas transações para conferência operacional rápida.
