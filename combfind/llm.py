import os
from typing import Protocol


class LLMBackend(Protocol):
    def chat(self, messages: list[dict], max_tokens: int | None = None, schema: str | None = None) -> str:
        ...


class LocalBackend:
    def __init__(self, model_path: str, n_ctx: int = 2048):
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError("llama-cpp-python is required: pip install 'combfind[llm]'")
        self._llm = Llama(model_path=model_path, n_ctx=n_ctx, verbose=False)

    def chat(self, messages: list[dict], max_tokens: int | None = None, schema: str | None = None) -> str:
        grammar = None
        if schema is not None:
            from llama_cpp import LlamaGrammar
            grammar = LlamaGrammar.from_json_schema(schema)
        result = self._llm.create_chat_completion(messages, max_tokens=max_tokens, grammar=grammar)
        return result["choices"][0]["message"]["content"].strip()


class OpenAIBackend:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai is required: pip install 'combfind[openai]'")
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._model = model or "gpt-4o-mini"

    def chat(self, messages: list[dict], max_tokens: int | None = None, schema: str | None = None) -> str:
        kwargs: dict = {}
        if schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.choices[0].message.content.strip()


def create_backend(mode: str, **kwargs) -> LLMBackend:
    if mode == "local":
        model = kwargs.get("llm_model")
        if not model:
            raise ValueError("llm_model is required for local mode")
        return LocalBackend(model_path=model, n_ctx=kwargs.get("llm_ctx") or 2048)
    if mode == "openai":
        return OpenAIBackend(
            base_url=os.environ.get("COMBFIND_LLM_BASE_URL"),
            api_key=os.environ.get("COMBFIND_LLM_API_KEY"),
            model=os.environ.get("COMBFIND_LLM_MODEL"),
        )
    raise ValueError(f"unknown LLM mode {mode!r}; valid: local, openai")
