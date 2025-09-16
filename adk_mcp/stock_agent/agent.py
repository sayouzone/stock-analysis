import os
from dotenv import load_dotenv

from stock_agent.tools import execute_bigquery_sql

from google.adk.agents import LlmAgent, SequentialAgent

load_dotenv()

MODEL_AGENT = "gemini-2.5-pro"

fundamentals_analysis_query_generator_agent = LlmAgent(
    name="StockFundamentalsAnalysisQuaryGenerateAgent",
    model=MODEL_AGENT,
    instruction="""
    You are a financial analysis agent. Your task is to analyze stock fundamentals data and provide insights.
    """,
    description="Generates a BigQuery SQL based on the user's question about Stocks fundamentals.",
    output_key="generated_sql",  # Stores output in state['generated_sql']
)

root_agent = SequentialAgent(
    name="StockAnalysisAgent",
    sub_agents=[fundamentals_analysis_query_generator_agent, trends_query_executor_agent],
    description="""A two-step pipeline that first generates a SQL query for Google Trends and then executes it. 
    Format the output as user friendly markdown format. Separete the SQL query and the interpretation of the results with a horizontal line.""",
)