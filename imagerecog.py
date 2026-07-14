from transformers import pipeline
from pathlib import Path


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

    def recognize(self, image_path : str):
        """
        Recognizes an image using facebook's detr resnet50 model
        :param image_path: Path to file. looks inside ./received_files as working directory. feel free to jump around :)
        :return: json of model result
        """
        try:
            model_output = self._recognizer(str(self._default_path / image_path))
        except Exception as e:
            raise RecognitionError(f"Couldn't recognize the image!\n{e}") from e
        return model_output

