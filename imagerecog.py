from transformers import pipeline
from pathlib import Path
import hashlib

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in Singleton._instances:
            Singleton._instances[cls] = super().__call__(*args, **kwargs)
        return Singleton._instances[cls]



class RecognitionError(Exception):
    pass


class ImageRecognition(metaclass=Singleton):
    def __init__(self):
        self._recognizer = pipeline("object-detection", model="facebook/detr-resnet-50")
        self._default_path = Path("received_files")
        self._RECOGNIZED_IMAGE_CACHE = {}

    def _get_digest(self, image_path : str):
        try:
            with open(image_path, 'rb') as f:
                return hashlib.file_digest(f, 'sha256')
        except Exception as e:
            print(f"Couldn't calculate file digest... {e}")
            return None
    def recognize(self, image_path : str):
        """
        Recognizes an image using facebook's detr resnet50 model
        :param image_path: Path to file. looks inside ./received_files as working directory. feel free to jump around :)
        :return: json of model result
        """
        model_output = self._RECOGNIZED_IMAGE_CACHE.get(self._get_digest(image_path))
        if model_output:
            return model_output
        try:
            model_output = self._recognizer(str(self._default_path / image_path))
        except Exception as e:
            raise RecognitionError(f"Couldn't recognize the image!\n{e}") from e
        return model_output
