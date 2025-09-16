from google import genai
from google.genai import types

import pandas as pd
import json
import os

tool_config = types.ToolConfig(
    function_calling_config=types.FunctionCallingConfig(
        mode="AUTO", allowed_function_names=[""]
    )
)
def analysis(stock : str, prompt: str):
    """
    Analyzes financial data using the Gemini API with a given prompt.
    Returns the raw JSON string from the API.
    """
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")

        # Configure the model to output JSON
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            tools=[]
            )
        
        client = genai.Client(api_key=api_key)

        full_prompt = f"{prompt}\n\nUse find_fnguide_data(stock) with {stock} and then analyze"

        # Use a model that explicitly supports JSON mode

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=full_prompt,
            config=generation_config,
        )
        
        # The response should be a valid JSON string, but we validate to be safe
        try:
            json.loads(response.text)  # type: ignore
            return response.text
        except (json.JSONDecodeError, TypeError):
            print(f"Gemini API (in JSON mode) returned a non-JSON response: {response.text}")
            error_response = {
                "summary": "AI가 유효하지 않은 형식의 응답을 반환했습니다.",
                "key_issues": "-",
                "risk_factors": "-",
                "investment_implication": "분석 오류"
            }
            return json.dumps(error_response, ensure_ascii=False)

    except Exception as e:
        print(f'Error during Gemini analysis: {e}')
        error_response = {
            "summary": "AI 분석 중 오류가 발생했습니다.",
            "key_issues": "-",
            "risk_factors": "-",
            "investment_implication": "분석 오류"
        }
        return json.dumps(error_response, ensure_ascii=False)
