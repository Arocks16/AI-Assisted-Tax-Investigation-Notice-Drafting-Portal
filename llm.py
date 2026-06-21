# LLM wrapper — calls Qwen2.5-7B-Instruct via Hugging Face Inference API

import os
from huggingface_hub import InferenceClient

os.environ["HUGGINGFACEHUB_API_TOKEN"] = "token here"


class LLM:
    """Wraps HF InferenceClient with an .invoke(prompt) interface."""

    def __init__(self):
        self._client = InferenceClient(token=os.environ["HUGGINGFACEHUB_API_TOKEN"])

    def invoke(self, prompt: str) -> str:
        """Send a prompt to the model and return the text response."""
        resp = self._client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="Qwen/Qwen2.5-7B-Instruct",
            max_tokens=512,
            temperature=0.2,
        )
        return resp.choices[0].message.content


# Singleton instance used by backend.py
llm = LLM()
