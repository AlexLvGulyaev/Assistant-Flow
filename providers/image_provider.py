from abc import ABC, abstractmethod
from typing import Any, Dict


class ImageProvider(ABC):
    @abstractmethod
    def generate_image(self, prompt: str) -> Dict[str, Any]:
        """
        Generate and save an image from prompt.
        Must return a standardized result dict.
        """
        raise NotImplementedError
