import os
from langchain_openai import ChatOpenAI

key = os.getenv("OPENROUTER_API_KEY")

class LLM:
    def __init__(self):
        self._model = ChatOpenAI(
            model="google/gemma-4-31b-it:free",
            openai_api_key= key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.0,
            max_tokens=2048,
        )

    def invoke(self, prompt: str) -> str:
        resp = self._model.invoke(prompt)
        return resp.content


llm = LLM()
