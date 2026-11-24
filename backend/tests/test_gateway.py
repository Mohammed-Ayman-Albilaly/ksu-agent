"""The gateway seam: one place that knows the provider, its key name and its limits."""

import pytest

import embed_chunks
import gateway
from embed_chunks import EmbeddingConfig


def chat_config(**overrides):
    values = {
        "provider": "gateway",
        "model": "DeepSeek-V4.1-Flash",
        "temperature": 0.0,
        "max_output_tokens": 700,
        "price_per_1m_input": 0.30,
        "price_per_1m_output": 1.20,
        "source_id": "ref-01",
        "base_url": "https://ai-gateway.seai-x.com/inference/v1",
        "api_key_env": "LLM_API_KEY",
        "json_mode": "json_object",
        "reasoning_effort": "none",
    }
    values.update(overrides)
    return __import__("answer").ChatConfig(**values)


def embed_config(**overrides):
    values = {
        "provider": "gateway",
        "model": "local-embedding-model",
        "dimensions": 1024,
        "max_input_tokens": 8192,
        "price_per_1m_tokens": 0.0,
        "tokenizer": "cl100k_base",
        "batch_size": 64,
        "batch_max_tokens": 200000,
        "base_url": "https://ai-gateway.seai-x.com/inference/v1",
        "api_key_env": "LLM_API_KEY",
        "send_dimensions": False,
    }
    values.update(overrides)
    return EmbeddingConfig(**values)


def test_the_key_is_read_from_the_variable_the_config_names(tmp_path):
    """A project key can be named anything; the code never hardcodes OPENAI_API_KEY."""
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=gw-test-value\n", encoding="utf-8")

    assert gateway.api_key(chat_config(), env_file) == "gw-test-value"


def test_an_absent_key_names_the_variable_and_never_its_value(tmp_path):
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        gateway.api_key(chat_config(), tmp_path / "absent.env")


def test_chat_asks_for_json_object_and_no_thinking():
    kwargs = gateway.chat_request(chat_config(), truncated_reply_ok=False)

    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["extra_body"] == {"reasoning_effort": "none"}


def test_chat_omits_the_reasoning_effort_when_none_is_configured():
    kwargs = gateway.chat_request(
        chat_config(reasoning_effort=""), truncated_reply_ok=False
    )

    assert "extra_body" not in kwargs


def test_a_client_carries_the_model_base_url_and_key_the_config_names(tmp_path):
    """The seam's central claim: the config, not the code, decides where a call goes.

    Both clients are built from the one config ``answer.load_config`` reads out of a TOML
    written here, and the key is the one ``api_key`` reads out of a .env written here, so
    nothing about either client is passed by hand.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=gw-test-value\n", encoding="utf-8")
    config_path = tmp_path / "chat.toml"
    config_path.write_text(
        "[chat]\n"
        'provider = "gateway"\n'
        'model = "DeepSeek-V4.1-Flash"\n'
        "temperature = 0.0\n"
        "max_output_tokens = 700\n"
        "price_per_1m_input = 0.30\n"
        "price_per_1m_output = 1.20\n"
        'source_id = "ref-01"\n'
        'base_url = "https://ai-gateway.seai-x.com/inference/v1"\n'
        'api_key_env = "LLM_API_KEY"\n'
        'json_mode = "json_object"\n'
        'reasoning_effort = "none"\n',
        encoding="utf-8",
    )
    config = __import__("answer").load_config(config_path)

    chat = gateway.make_chat_client(config, env_file)
    assert chat.model_name == config.model
    assert chat.openai_api_base == config.base_url
    assert chat.openai_api_key.get_secret_value() == "gw-test-value"

    embedder = gateway.make_embed_client(config, env_file)
    assert embedder.model == config.model
    assert embedder.openai_api_base == config.base_url


def test_embed_sends_no_dimensions_by_default():
    """The gateway model may reject a parameter it does not know; it is opt-in."""
    kwargs = gateway.embed_kwargs(embed_config())

    assert "dimensions" not in kwargs
    assert kwargs["encoding_format"] == "float"


def test_embed_sends_the_dimensions_when_the_config_asks():
    kwargs = gateway.embed_kwargs(embed_config(send_dimensions=True))

    assert kwargs["dimensions"] == 1024


def test_the_config_less_call_shape_still_works_from_embed_chunks(tmp_path):
    """embed_chunks re-exports the helpers, and its callers pass no config.

    app/auth/config.py and app/route_token.py import load_env_file and
    DEFAULT_ENV_FILE from embed_chunks, and its own api_key(env_file) names no config.
    """
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=legacy-value\n", encoding="utf-8")

    assert embed_chunks.api_key(env_file) == "legacy-value"
