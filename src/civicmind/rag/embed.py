"""Sentence embeddings with a pinned, pretrained model (no training): all-MiniLM-L6-v2 on ONNX.

The model files live in ``data/models/`` (git-ignored; downloaded only with the owner's approval)
and are pinned here by Hugging Face commit and SHA-256. ``MiniLMEncoder`` reads each file once
through a verified handle (``catalog.safe_fs``), refuses bytes that do not match the pinned
hash, and builds the ONNX Runtime session and tokenizer from those exact bytes.

Inference follows the model card: WordPiece tokens truncated to 256, mean pooling over the
attention mask, then L2 normalisation, so a dot product is the cosine similarity. ONNX Runtime
runs on CPU with one intra-op thread and sequential execution, which keeps results reproducible
on one machine; bit-identical vectors across CPUs or library versions are not claimed.

``onnxruntime`` and ``tokenizers`` are optional (extra ``rag-embed``) and imported on use.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from civicmind.catalog.safe_fs import read_verified

MODELS_DIR = "data/models"


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    revision: str
    license: str
    files: dict[str, str]  # relative path inside the revision folder -> SHA-256
    dim: int
    max_tokens: int
    pooling: str = "mean"
    normalize: bool = True

    @property
    def folder(self) -> str:
        return f"{MODELS_DIR}/{self.model_id.split('/')[-1]}/{self.revision}"

    def to_dict(self) -> dict:
        return asdict(self)


MINILM = ModelSpec(
    model_id="sentence-transformers/all-MiniLM-L6-v2",
    revision="1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
    license="Apache-2.0",
    files={
        # LFS SHA-256 from the Hub API for this revision (the HTTP ETag is the Xet hash).
        "onnx/model.onnx": "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452",
        "tokenizer.json": "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037",
    },
    dim=384,
    max_tokens=256,
)


class EmbeddingUnavailable(RuntimeError):
    """The embedding runtime or the pinned model files are missing or do not verify."""


class Encoder(Protocol):
    spec: ModelSpec

    def encode(self, texts: list[str]) -> np.ndarray: ...


class MiniLMEncoder:
    def __init__(self, root: str | Path, spec: ModelSpec = MINILM, batch_size: int = 32):
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:
            raise EmbeddingUnavailable(
                "dense retrieval needs the optional 'rag-embed' extra (onnxruntime, tokenizers)"
            ) from exc
        self.spec, self.batch_size = spec, batch_size
        blobs = {}
        for rel, expected in spec.files.items():
            path = f"{spec.folder}/{rel}"
            try:
                data = read_verified(root, path, (MODELS_DIR,), max_bytes=512 * 1024 * 1024)
            except (OSError, ValueError) as exc:
                raise EmbeddingUnavailable(f"model file {path} unavailable ({exc})") from None
            if hashlib.sha256(data).hexdigest() != expected:
                raise EmbeddingUnavailable(f"model file {path} does not match its pinned SHA-256")
            blobs[rel] = data
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        self.session = ort.InferenceSession(
            blobs["onnx/model.onnx"], options, providers=["CPUExecutionProvider"]
        )
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.tokenizer = Tokenizer.from_str(blobs["tokenizer.json"].decode("utf-8"))
        self.tokenizer.enable_truncation(max_length=spec.max_tokens)
        self.tokenizer.enable_padding()
        self.versions = {"onnxruntime": ort.__version__}

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.spec.dim), dtype=np.float32)
        for start in range(0, len(texts), self.batch_size):
            batch = self.tokenizer.encode_batch(texts[start : start + self.batch_size])
            ids = np.array([e.ids for e in batch], dtype=np.int64)
            mask = np.array([e.attention_mask for e in batch], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self.session.run(None, feed)[0]  # (batch, tokens, dim)
            weights = mask[:, :, None].astype(np.float32)
            pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            out[start : start + len(batch)] = pooled / np.clip(norms, 1e-12, None)
        return out


__all__ = [
    "MINILM",
    "MODELS_DIR",
    "EmbeddingUnavailable",
    "Encoder",
    "MiniLMEncoder",
    "ModelSpec",
]
