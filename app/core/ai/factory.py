from app.core.ai.ollama_provider import OllamaProvider

class AIFactory:

    @staticmethod
    def get_provider():
        return OllamaProvider()
