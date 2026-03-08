"""Tests integrations imports."""

import sys
import importlib
import pytest

import agentdbg.integrations as integrations
from agentdbg.integrations._error import MissingOptionalDependencyError


def has_module(name):
    return importlib.util.find_spec(name) is not None


INTEGRATIONS = [  # name, dependency
    ("crewai", "crewai"),
    ("langchain", "langchain_core"),
    ("openai_agents", "agents"),
]


@pytest.fixture
def reload_integrations():
    sys.modules.pop("agentdbg.integrations.crewai", None)
    sys.modules.pop("agentdbg.integrations.langchain", None)

    integrations.__dict__.pop("crewai", None)
    integrations.__dict__.pop("langchain", None)
    integrations.__dict__.pop("AgentDbgLangChainCallbackHandler", None)

    importlib.reload(integrations)


def test_no_eager_imports(reload_integrations):
    assert "agentdbg.integrations.crewai" not in sys.modules
    assert "agentdbg.integrations.langchain" not in sys.modules
    assert "AgentDbgLangChainCallbackHandler" not in sys.modules


@pytest.mark.parametrize("name, dependency", INTEGRATIONS)
def test_lazy_module_imports(reload_integrations, name, dependency):

    if importlib.util.find_spec(dependency) is None:
        pytest.skip(f"{dependency} not installed")

    mod = getattr(integrations, name)

    assert f"agentdbg.integrations.{name}" in sys.modules
    assert mod is sys.modules[f"agentdbg.integrations.{name}"]


@pytest.mark.skipif(
    importlib.util.find_spec("langchain_core") is None, reason="langchain not installed"
)
def test_lazy_attribute_imports(reload_integrations):
    cls = integrations.AgentDbgLangChainCallbackHandler
    assert "agentdbg.integrations.langchain" in sys.modules
    assert cls.__name__ == "AgentDbgLangChainCallbackHandler"
    assert (
        cls
        is sys.modules[
            "agentdbg.integrations.langchain"
        ].AgentDbgLangChainCallbackHandler
    )


def test_unknown_attribute_raises_attribute_error():
    with pytest.raises(AttributeError):
        integrations.this_does_not_exist


def test_dir_includes_all_attributes():
    dir_ = dir(integrations)
    for name in integrations.__all__:
        assert name in dir_


def test_missing_dependency_raises(monkeypatch):
    integrations.__dict__.pop("AgentDbgLangChainCallbackHandler", None)
    integrations.__dict__.pop("langchain", None)
    sys.modules.pop("agentdbg.integrations.langchain", None)

    real_import_module = importlib.import_module

    def fake_import_module(name, package=None):
        if name == "agentdbg.integrations.langchain":
            raise MissingOptionalDependencyError("langchain_core not installed")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(
        MissingOptionalDependencyError, match="langchain_core not installed"
    ):
        _ = integrations.AgentDbgLangChainCallbackHandler
