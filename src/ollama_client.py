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
                "temperature": 0.1,
            },
        }
        response = requests.post(url, json=payload, timeout=240)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def embed(self, text: str, model: str = EMBED_MODEL) -> list[float]:
        # Новые версии Ollama предпочитают /api/embed,
        # но для совместимости оставляем fallback на /api/embeddings.
        # Удаляем только управляющие непечатаемые символы,
        # но НЕ вырезаем кириллицу и обычный русский текст.
        text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
        max_chars = 2000
        if len(text) > max_chars:
            text = text[:max_chars]
        #print(f"DEBUG: embedding text length {len(text)}")
        payload_new = {
            "model": model,
            "input": text,
        }
        try:
            url_new = f"{self.host}/api/embed"
            response = requests.post(url_new, json=payload_new, timeout=240)
            response.raise_for_status()
            data = response.json()
            emb = data.get("embeddings")
            if emb and isinstance(emb, list):
                return emb[0]
        except Exception:
            pass

        url_old = f"{self.host}/api/embeddings"
        payload_old = {
            "model": model,
            "prompt": text,
        }
        response = requests.post(url_old, json=payload_old, timeout=240)
        response.raise_for_status()
        data = response.json()
        return data["embedding"]


ollama_client = OllamaClient()
