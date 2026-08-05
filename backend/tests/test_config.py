from eventforge.core.config import Settings


def test_api_keys_strip_trailing_newlines_and_spaces() -> None:
    settings = Settings(
        openai_api_key="sk-test\n",
        anthropic_api_key=" sk-ant-test \n",
    )
    assert settings.openai_api_key == "sk-test"
    assert settings.anthropic_api_key == "sk-ant-test"


def test_postgres_password_strips_whitespace() -> None:
    settings = Settings(postgres_password=" changeme\n")
    assert settings.postgres_password == "changeme"
