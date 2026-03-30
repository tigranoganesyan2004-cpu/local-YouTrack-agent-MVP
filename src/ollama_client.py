import json
import requests
import re
from src.config import OLLAMA_HOST, GEN_MODEL, EMBED_MODEL


class OllamaClient:
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip("/")

    def generate(self, prompt: str, model: str = GEN_MODEL) -> str:
        url = f"{self.host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0,
            },
        }
        response = requests.post(url, json=payload, timeout=240)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def generate_stream(self, prompt: str, model: str = GEN_MODEL):
        """
        Стриминговая генерация.
        Возвращает генератор кусков текста от Ollama.

        Важно:
        - не глотаем ошибки молча;
        - верхний слой сам решает, как делать fallback.
        """
        url = f"{self.host}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": 0,
            },
        }

        with requests.post(url, json=payload, stream=True, timeout=240) as response:
            response.raise_for_status()

            for raw_line in response.iter_lines():
                if not raw_line:
                    continue

                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                token = chunk.get("response", "")
                if token:
                    yield token

                if chunk.get("done", False):
                    break

    def embed(self, text: str, model: str = EMBED_MODEL) -> list[float]:
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text).strip()

        if not text:
            raise ValueError("Пустой текст для embedding.")

        max_chars = 2000
        if len(text) > max_chars:
            text = text[:max_chars]

        first_error = None

        try:
            url_new = f"{self.host}/api/embed"
            payload_new = {
                "model": model,
                "input": text,
            }

            response = requests.post(url_new, json=payload_new, timeout=240)
            response.raise_for_status()

            data = response.json()
            embeddings = data.get("embeddings")

            if isinstance(embeddings, list) and len(embeddings) > 0:
                if isinstance(embeddings[0], list) and len(embeddings[0]) > 0:
                    return embeddings[0]

            first_error = RuntimeError("Новый endpoint /api/embed не вернул embeddings.")
        except Exception as e:
            first_error = e

        try:
            url_old = f"{self.host}/api/embeddings"
            payload_old = {
                "model": model,
                "prompt": text,
            }

            response = requests.post(url_old, json=payload_old, timeout=240)
            response.raise_for_status()

            data = response.json()
            embedding = data.get("embedding")

            if isinstance(embedding, list) and len(embedding) > 0:
                return embedding

            raise RuntimeError("Старый endpoint /api/embeddings не вернул embedding.")
        except Exception as e:
            raise RuntimeError(
                f"Не удалось получить embedding через Ollama. "
                f"Модель: {model}. "
                f"Ошибка /api/embed: {first_error}. "
                f"Ошибка /api/embeddings: {e}"
            ) from e


ollama_client = OllamaClient()