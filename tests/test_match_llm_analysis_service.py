from cs2eye.core.config import Settings


def test_model_is_configurable() -> None:
    configured = Settings(_env_file=None, match_llm_model="custom-model")
    assert configured.match_llm_model == "custom-model"


def test_ollama_host_and_qwen_model_are_configurable() -> None:
    configured = Settings(
        _env_file=None, ollama_host="http://ollama:11434", match_llm_model="future:model",
    )
    assert configured.ollama_host == "http://ollama:11434"
    assert configured.match_llm_model == "future:model"
