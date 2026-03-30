from __future__ import annotations

import asyncio
import json
import logging

import httpx

from docx_automation_service.core.config import settings
from docx_automation_service.integrations.base import Rewriter

logger = logging.getLogger(__name__)

# Anti-AIGC blacklist terms (for logging & detection)
BLACKLIST_TERMS = {
    "总而言之": "总结",
    "值得注意的是": "需要注意",
    "不可避免地": "必然",
    "由此产生的": "导致",
    "神经符号": "符号",
    "架构": "系统结构",
    "代偿": "弥补",
    "坍塌": "失效",
    "隔离层": "拦截器",
    "维度": "方面",
    "范式": "方案",
    "伦理约束": "规则",
}


class SiliconFlowRewriter(Rewriter):
    def __init__(self) -> None:
        self._base_url = settings.siliconflow_base_url.rstrip("/")
        self._api_key = settings.siliconflow_api_key
        self._model = settings.siliconflow_model

    async def rewrite(
        self,
        text: str,
        topic_hint: str | None = None,
        preserve_terms: list[str] | None = None,
    ) -> str:
        if not self._api_key:
            return text

        preserve_terms = preserve_terms or []
        hint = topic_hint or "学术论文"

        # Four-pillar anti-AIGC strategy prompt
        # Pillar 1: Persona shift & active voice (第一人称/主动语态)
        # Pillar 2: Burstiness injection (长短句交替)
        # Pillar 3: Engineering detail & intellectual hesitation (工程细节与不确定性)
        # Pillar 4: Blacklist word removal (黑名单词汇剔除)
        
        system_prompt = (
            "你扮演一位有10年工程与研究经验的资深工科博士。"
            "你的改写目标是让文本读起来像真实人类的思考，而非机器。\n"
            "改写时采用第一人称或主动语态（我们设计、我们实现，而非被设计、被实现）。"
            "强制创造长短句交替的节奏：长复杂句后必跟极简短句。"
            "暴露工程现实与妥协：说出设计中的约束、失败的尝试、成本的取舍。"
            "彻底删除这些AI高频词：总而言之、值得注意的是、不可避免地、由此产生的、"
            "神经符号、代偿、坍塌、架构范式、维度隔离层、伦理约束。"
            "用朴实词汇替换：范式→方案，维度→方面，隔离层→拦截器，代偿→弥补。"
            "保留所有引文标记、数学符号、代码片段、变量名。绝不编造事实。"
        )

        user_prompt = {
            "task": "rewrite_with_anti_aigc_strategy",
            "topic": hint,
            "preserve_terms": preserve_terms,
            "input_text": text,
            "constraints": [
                "【必须保留】核心论意100%，数据准确，引文标记（[1]、(Doe, 2024)）绝不改动。",
                "【结构突变】强制长短句交替：复杂逻辑（长句）后必跟7字以内短句。示例：'这是关键限制。'或'系统必须拒绝。'",
                "【工程细节】每个关键概念加入工程现实：'虽然理想情况是X，但受制于成本/算力/时间，我们采用了Y'，或'一开始尝试了A，失败原因是B，改用现方案'。",
                "【代码保留】涉及JSON、SQL、正则、配置的内容：不删除、不模糊。具体展示格式示例或语句片段。",
                "【词汇控制】单句最多3个专业术语，用平实语言解释。",
                "【黑名单剔除】完全删除：总而言之→总结，值得注意→需要注意，不可避免→必然，由此产生→导致，神经符号→符号，架构→系统结构，代偿→弥补，坍塌→失效。",
                "【排比禁用】不用排比对仗和宏大叙事。改用技术文档风格：主谓宾清晰，段落逻辑递进，句式多样。",
                "【输出格式】仅返回改写文本，无前缀、无解释、无标记。",
            ],
        }

        payload = {
            "model": self._model,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(
            connect=min(15.0, settings.siliconflow_timeout_seconds),
            read=settings.siliconflow_timeout_seconds,
            write=30.0,
            pool=30.0,
        )

        max_attempts = max(1, settings.siliconflow_max_retries + 1)
        backoff = max(0.1, settings.siliconflow_retry_backoff_seconds)
        data: dict = {}

        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    break
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                    if attempt >= max_attempts:
                        logger.warning(
                            "siliconflow timeout after retries | attempts=%s | text_len=%s | fallback=original",
                            attempt,
                            len(text),
                        )
                        return text
                    sleep_s = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "siliconflow timeout | attempt=%s/%s | wait=%.2fs | error=%s",
                        attempt,
                        max_attempts,
                        sleep_s,
                        exc,
                    )
                    await asyncio.sleep(sleep_s)
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    # Retry transient upstream issues.
                    if status in {408, 429, 500, 502, 503, 504} and attempt < max_attempts:
                        sleep_s = backoff * (2 ** (attempt - 1))
                        logger.warning(
                            "siliconflow transient http error | status=%s | attempt=%s/%s | wait=%.2fs",
                            status,
                            attempt,
                            max_attempts,
                            sleep_s,
                        )
                        await asyncio.sleep(sleep_s)
                        continue

                    logger.error(
                        "siliconflow non-retryable http error | status=%s | fallback=original",
                        status,
                    )
                    return text
                except Exception as exc:  # noqa: BLE001
                    logger.exception("siliconflow unknown error | fallback=original | error=%s", exc)
                    return text

        choices = data.get("choices") or []
        if not choices:
            return text

        content = choices[0].get("message", {}).get("content", "")
        result = content.strip() or text
        
        # Log detected blacklist terms (for quality assurance)
        found_blacklist = [term for term in BLACKLIST_TERMS if term in result]
        if found_blacklist:
            logger.warning(
                "rewritten text contains blacklist terms (should be auto-cleaned by LLM) | terms=%s",
                found_blacklist,
            )
        
        return result
