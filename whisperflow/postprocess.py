"""Optional post-processing hooks for Whisperflow."""

from __future__ import annotations

from typing import Any

from whisperflow.errors import ConfigError


def postprocess(text: str, config: dict[str, Any]) -> str:
    """Optionally post-process transcript text based on local provider config."""
    postprocess_config = config.get("postprocess")
    if not isinstance(postprocess_config, dict):
        raise ConfigError("Config key 'postprocess' must be an object.")

    if not postprocess_config.get("enabled", False):
        return text

    provider = postprocess_config.get("provider")
    profile = postprocess_config.get("profile")
    if not isinstance(provider, str) or not provider:
        raise ConfigError("Post-processing is enabled but no provider is configured.")
    if not isinstance(profile, str) or not profile:
        raise ConfigError("Post-processing is enabled but no profile is configured.")

    provider_configs = postprocess_config.get("providers")
    if not isinstance(provider_configs, dict):
        raise ConfigError(
            "Post-processing is enabled but no local provider configuration was found. "
            "Add 'postprocess.providers' to the config or disable post-processing."
        )

    provider_config = provider_configs.get(provider)
    if not isinstance(provider_config, dict):
        raise ConfigError(
            f"Post-processing is enabled but provider '{provider}' is not configured. "
            "Add a matching entry under 'postprocess.providers'."
        )

    profiles = provider_config.get("profiles")
    if not isinstance(profiles, dict) or profile not in profiles:
        raise ConfigError(
            "Post-processing is enabled but profile "
            f"'{profile}' is not configured for provider '{provider}'. "
            f"Add it under 'postprocess.providers.{provider}.profiles'."
        )

    return text


__all__ = ["postprocess"]
