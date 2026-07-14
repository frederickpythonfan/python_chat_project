from transformers import pipeline
from pathlib import Path
import hashlib
import logging
import json

logger = logging.getLogger(__name__)


class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in Singleton._instances:
            Singleton._instances[cls] = super().__call__(*args, **kwargs)
        return Singleton._instances[cls]



class RecognitionError(Exception):
    pass

_DEFAULT_CACHE = "image_cache.json"

class ImageRecognition(metaclass=Singleton):
    def __init__(self):
        logger.info("Loading object-detection model facebook/detr-resnet-50 ...")
        self._recognizer = pipeline("object-detection", model="facebook/detr-resnet-50")
        self._RECOGNIZED_IMAGE_CACHE : dict[str, dict]= {}
        self.load_cache(_DEFAULT_CACHE)
        logger.info("Model loaded, ready to recognize images")

    def _get_digest(self, image_path : str):
        try:
            with open(image_path, 'rb') as f:
                return hashlib.file_digest(f, 'sha256').hexdigest()
        except Exception as e:
            logger.error(f"Couldn't calculate file digest... {e}")
            return None
    def recognize(self, image_path : str):
        """
        Recognizes an image using facebook's detr resnet50 model
        :param image_path: Path to file. looks inside ./received_files as working directory. feel free to jump around :)
        :return: json of model result
        """
        digest = self._get_digest(image_path)
        model_output = self._RECOGNIZED_IMAGE_CACHE.get(digest)

        if model_output:
            logger.info("Cache hit for %s -- returning cached recognition result", image_path)
            return model_output

        logger.info("Cache miss for %s -- running recognition model", image_path)
        try:
            model_output = self._recognizer(str(image_path))
        except Exception as e:
            logger.error("Recognition failed for %s: %s", image_path, e)
            raise RecognitionError(f"Couldn't recognize the image!\n{e}") from e
        self._RECOGNIZED_IMAGE_CACHE[digest] = model_output
        logger.info("Recognition succeeded for %s -- found %d object(s)",
                    image_path, len(model_output) if model_output else 0)
        return model_output

    def save_cache_to_file(self, filename: str=_DEFAULT_CACHE):
        with open(filename, "w") as file:
            json.dump(self._RECOGNIZED_IMAGE_CACHE, file, indent=4)

    def load_cache(self, filename: str=_DEFAULT_CACHE):
        try:
            with open(filename, "w") as file:
                self._RECOGNIZED_IMAGE_CACHE = json.load(file)
        except Exception:
            self._RECOGNIZED_IMAGE_CACHE = {}

