from eventforge.core.config import Settings


def test_use_mock_external_apis_defaults_true_in_local() -> None:
    settings = Settings(environment="local", mock_external_apis=None)
    assert settings.use_mock_external_apis is True


def test_use_mock_external_apis_defaults_false_in_prod() -> None:
    settings = Settings(environment="prod", mock_external_apis=None)
    assert settings.use_mock_external_apis is False


def test_use_mock_external_apis_explicit_override() -> None:
    settings = Settings(environment="local", mock_external_apis=False)
    assert settings.use_mock_external_apis is False


def test_mock_external_apis_empty_env_treated_as_auto() -> None:
    settings = Settings(environment="local", mock_external_apis="")
    assert settings.use_mock_external_apis is True
