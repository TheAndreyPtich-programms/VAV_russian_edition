import json
from vosk import Model, KaldiRecognizer

class VoskRecognizer:
    def __init__(self, model_path: str = None, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.model = None
        self.rec = None
        if model_path:
            self.load_model(model_path)

    def load_model(self, model_path: str):
        if self.rec:
            self.rec = None
        if self.model:
            self.model = None

        self.model = Model(model_path)
        self.rec = KaldiRecognizer(self.model, self.sample_rate)
        self.rec.Reset()
        print(f"Модель загружена: {model_path}")

    def accept_waveform(self, data):
        if self.rec is None:
            return False
        return self.rec.AcceptWaveform(data)

    def result(self):
        if self.rec is None:
            return {"text": ""}
        return json.loads(self.rec.Result())