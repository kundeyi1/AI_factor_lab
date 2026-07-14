import json
import logging
import re

import requests

from server.ai.prompts import FACTOR_GENERATOR_PROMPT
from server.config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL, OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)


PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "api_key": DEEPSEEK_API_KEY,
        "base_url": "https://api.deepseek.com/chat/completions",
        "model": DEEPSEEK_MODEL,
    },
    "openai": {
        "label": "OpenAI",
        "api_key": OPENAI_API_KEY,
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model": OPENAI_MODEL,
    },
}


class FactorGenerator:
    def generate_factor(
        self,
        user_prompt: str,
        history: list[dict[str, str]] | None = None,
        api_key: str | None = None,
        provider: str = "deepseek",
    ) -> dict[str, str]:
        provider = provider or "deepseek"
        config = PROVIDERS.get(provider)
        if not config:
            supported = "、".join(item["label"] for item in PROVIDERS.values())
            raise ValueError(f"不支持的 AI 供应商：{provider}。当前支持：{supported}。")

        key = api_key or config["api_key"]
        if not key:
            env_name = "DEEPSEEK_API_KEY" if provider == "deepseek" else "OPENAI_API_KEY"
            raise ValueError(f"未提供 {config['label']} API Key。请在左下角输入，或设置环境变量 {env_name}。")

        messages = self._build_messages(user_prompt, history or [])
        return self._call_chat_completions(config["base_url"], config["model"], messages, key, config["label"])

    def _build_messages(self, user_prompt: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": FACTOR_GENERATOR_PROMPT}]
        for item in history[-12:]:
            role = item.get("role", "user")
            if role == "model":
                role = "assistant"
            if role in {"user", "assistant"} and item.get("content"):
                messages.append({"role": role, "content": item["content"]})
        messages.append({"role": "user", "content": f"用户需求：{user_prompt}"})
        return messages

    def _call_chat_completions(
        self,
        url: str,
        model: str,
        messages: list[dict[str, str]],
        api_key: str,
        provider_label: str,
    ) -> dict[str, str]:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.1},
            timeout=60,
        )
        if response.status_code >= 400:
            raise ConnectionError(f"{provider_label} API 调用失败（{response.status_code}）：{response.text[:300]}")

        payload = response.json()
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise ValueError(f"{provider_label} API 返回为空。")
        return self._parse_json_response(content)

    def _parse_json_response(self, text: str) -> dict[str, str]:
        cleaned = text.strip().replace("```json", "").replace("```", "").strip()
        if not cleaned.startswith("{"):
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            cleaned = match.group(0) if match else cleaned

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("AI response is not valid JSON: %s", text)
            raise ValueError("AI 返回内容不是有效 JSON。") from exc

        required = {"name", "expression", "description"}
        missing = required - set(data)
        if missing:
            raise ValueError(f"AI 返回缺少字段：{', '.join(sorted(missing))}")
        return {key: str(data[key]).strip() for key in required}


factor_generator = FactorGenerator()
