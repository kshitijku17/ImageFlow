from __future__ import annotations
import logging
from pathlib import Path
from typing import Union
from PIL import Image

logger = logging.getLogger(__name__)

class CLIPModelManager:
    """
    Singleton / Cached Manager for OpenCLIP models.
    - Loads the model and preprocess pipeline only once.
    - Uses CUDA/GPU if available, falling back to CPU.
    - Generates normalized embeddings for images and text queries.
    - Handles errors gracefully without crashing the application.
    """
    _instance: CLIPModelManager | None = None

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k"):
        self.model_name = model_name
        self.pretrained = pretrained
        self.device = "cpu"
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self._is_loaded = False
        self._load_error: str | None = None

    @classmethod
    def get_instance(cls, model_name: str = "ViT-B-32", pretrained: str = "laion2b_s34b_b79k") -> CLIPModelManager:
        if cls._instance is None:
            cls._instance = cls(model_name=model_name, pretrained=pretrained)
        return cls._instance

    def load_model(self) -> bool:
        """Loads the OpenCLIP model and tokenizer onto the best available device."""
        if self._is_loaded and self.model is not None:
            return True

        try:
            import torch
            import open_clip

            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading OpenCLIP ({self.model_name}, pretrained: {self.pretrained}) on device: {self.device}")

            model, _, preprocess = open_clip.create_model_and_transforms(
                self.model_name,
                pretrained=self.pretrained,
                device=self.device
            )
            tokenizer = open_clip.get_tokenizer(self.model_name)

            model.eval()
            self.model = model
            self.preprocess = preprocess
            self.tokenizer = tokenizer
            self._is_loaded = True
            self._load_error = None
            logger.info("OpenCLIP model loaded successfully.")
            return True
        except Exception as e:
            self._is_loaded = False
            self._load_error = str(e)
            logger.error(f"Failed to load OpenCLIP model: {e}", exc_info=True)
            return False

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def get_embedding_dimension(self) -> int | None:
        """Returns the output feature dimension of the loaded model."""
        if not self.ensure_loaded():
            return None
        try:
            # ViT-B-32 is 512-dim
            if hasattr(self.model, "visual") and hasattr(self.model.visual, "output_dim"):
                return self.model.visual.output_dim
            if hasattr(self.model, "text_projection"):
                return self.model.text_projection.shape[1]
            return 512
        except Exception:
            return 512

    def ensure_loaded(self) -> bool:
        if not self._is_loaded:
            return self.load_model()
        return True

    def get_image_embedding(self, image_input: Union[str, Path, Image.Image]) -> list[float] | None:
        """
        Extracts a normalized feature embedding vector from an image file path or PIL Image.
        Returns a Python list of floats (unit length) or None on failure.
        """
        if not self.ensure_loaded():
            logger.error("Cannot compute image embedding: model is not loaded.")
            return None

        try:
            import torch

            if isinstance(image_input, (str, Path)):
                img_path = Path(image_input)
                if not img_path.exists():
                    logger.error(f"Image not found: {img_path}")
                    return None
                image = Image.open(img_path).convert("RGB")
            elif isinstance(image_input, Image.Image):
                image = image_input.convert("RGB")
            else:
                logger.error(f"Unsupported image input type: {type(image_input)}")
                return None

            tensor = self.preprocess(image).unsqueeze(0).to(self.device)

            with torch.no_grad():
                image_features = self.model.encode_image(tensor)
                image_features /= image_features.norm(dim=-1, keepdim=True)
                embedding = image_features.squeeze(0).cpu().tolist()

            return embedding
        except Exception as e:
            logger.error(f"Error generating image embedding: {e}", exc_info=True)
            return None

    def get_text_embedding(self, text: str) -> list[float] | None:
        """
        Extracts a normalized feature embedding vector for a text query.
        Returns a Python list of floats (unit length) or None on failure.
        """
        if not self.ensure_loaded():
            logger.error("Cannot compute text embedding: model is not loaded.")
            return None

        if not text or not text.strip():
            logger.warning("Empty text query passed for embedding.")
            return None

        try:
            import torch

            tokens = self.tokenizer([text.strip()]).to(self.device)

            with torch.no_grad():
                text_features = self.model.encode_text(tokens)
                text_features /= text_features.norm(dim=-1, keepdim=True)
                embedding = text_features.squeeze(0).cpu().tolist()

            return embedding
        except Exception as e:
            logger.error(f"Error generating text embedding: {e}", exc_info=True)
            return None


# Global convenience helper functions
def get_model_manager() -> CLIPModelManager:
    return CLIPModelManager.get_instance()

def get_image_embedding(image_input: Union[str, Path, Image.Image]) -> list[float] | None:
    return CLIPModelManager.get_instance().get_image_embedding(image_input)

def get_text_embedding(text: str) -> list[float] | None:
    return CLIPModelManager.get_instance().get_text_embedding(text)
