from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("YIAI_DB_PATH", "./data/yiai-center.sqlite")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    default_model: str = os.getenv("DEEPSEEK_DEFAULT_MODEL", "deepseek-v4-flash")
    thinking_effort: str = os.getenv("DEEPSEEK_THINKING_EFFORT", "high")
    flash_cache_hit_usd_per_m: float = float(
        os.getenv("DEEPSEEK_FLASH_CACHE_HIT_USD_PER_M", "0.0028")
    )
    flash_cache_miss_usd_per_m: float = float(
        os.getenv("DEEPSEEK_FLASH_CACHE_MISS_USD_PER_M", "0.14")
    )
    flash_output_usd_per_m: float = float(
        os.getenv("DEEPSEEK_FLASH_OUTPUT_USD_PER_M", "0.28")
    )

    def validate_model_policy(self) -> None:
        if self.default_model != "deepseek-v4-flash":
            raise RuntimeError(
                "V0.5.0-V0.5.5 only permits deepseek-v4-flash for ordinary runs"
            )
        if self.thinking_effort not in {"high", "max"}:
            raise RuntimeError("DeepSeek thinking effort must be high or max")


settings = Settings()

