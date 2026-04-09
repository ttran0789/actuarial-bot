"""Swappable LLM client — supports OpenAI, Azure OpenAI, and any OpenAI-compatible API."""

import logging
from typing import Optional
from openai import OpenAI, AzureOpenAI

log = logging.getLogger("actuarial_bot.llm")


def create_llm_client(config: dict) -> tuple[OpenAI, str]:
    """Create an LLM client from config. Returns (client, model_name).

    Config structure (under 'ai' key):
        provider: "openai" | "azure" | "custom"
        api_key: "..."
        model: "gpt-4o"

        # Azure-specific
        azure_endpoint: "https://your-resource.openai.azure.com/"
        azure_deployment: "your-deployment-name"
        azure_api_version: "2024-10-21"

        # Custom OpenAI-compatible endpoint (Ollama, LM Studio, vLLM, etc.)
        base_url: "http://localhost:11434/v1"
    """
    provider = config.get("provider", "openai").lower()
    api_key = config.get("api_key", "")
    model = config.get("model", "gpt-4o")

    if provider == "azure":
        endpoint = config["azure_endpoint"]
        api_version = config.get("azure_api_version", "2024-10-21")
        deployment = config.get("azure_deployment", model)

        log.info("Connecting to Azure OpenAI at %s (deployment: %s)", endpoint, deployment)
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        return client, deployment

    elif provider == "custom":
        base_url = config["base_url"]
        log.info("Connecting to custom endpoint at %s (model: %s)", base_url, model)
        client = OpenAI(
            api_key=api_key or "not-needed",
            base_url=base_url,
        )
        return client, model

    else:  # openai
        log.info("Connecting to OpenAI API (model: %s)", model)
        client = OpenAI(api_key=api_key)
        return client, model
