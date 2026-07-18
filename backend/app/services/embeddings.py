from typing import Protocol

import numpy as np


class Embedder(Protocol):
    def token_count(self, text: str) -> int: ...

    def encode_passages(self, texts: list[str]) -> np.ndarray: ...

    def encode_query(self, text: str) -> np.ndarray: ...


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def token_count(self, text: str) -> int:
        model = self._load()
        return len(model.tokenizer.encode(text, add_special_tokens=False))

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        values = [f"passage: {text}" for text in texts]
        return np.asarray(
            model.encode(values, normalize_embeddings=True, convert_to_numpy=True),
            dtype=np.float32,
        )

    def encode_query(self, text: str) -> np.ndarray:
        model = self._load()
        return np.asarray(
            model.encode(
                [f"query: {text}"], normalize_embeddings=True, convert_to_numpy=True
            )[0],
            dtype=np.float32,
        )
