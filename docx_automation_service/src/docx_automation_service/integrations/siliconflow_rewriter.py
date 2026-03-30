"""Layer 2 – Semantic Deep Restructuring via LLM rewriting.

Implements the second layer of the three-layer anti-plagiarism engine.

Strategy: Academic-corpus-informed iterative rewriting using DeepSeek-V3/R1
via the SiliconFlow API.

The prompt logic is inspired by ``gpt_academic``'s ``reduce_aigc.py``:
- Force the model to **break uniform sentence patterns**.
- **Introduce academic term variants** (not always the canonical form).
- **Simulate human researcher writing imperfections** (varying paragraph
  lengths, casual connectors, engineering hedges).
- Apply a curated **blacklist word substitution table** for high-frequency
  AI-generated terms.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from docx_automation_service.core.config import settings
from docx_automation_service.integrations.base import Rewriter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blacklist: AI high-frequency terms → natural replacements
# Sourced from empirical analysis of GPTZero / Turnitin flagging patterns.
# ---------------------------------------------------------------------------
BLACKLIST_TERMS: dict[str, str] = {
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
    "综上所述": "总结来看",
    "不言而喻": "显然",
    "多维度": "多方面",
}

# ---------------------------------------------------------------------------
# System prompt – Ten-year engineering researcher persona
# Inspired by gpt_academic reduce_aigc.py four-pillar strategy
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    "你扮演一位有10年工程与研究经验的资深工科博士。"
    "你的改写目标是让文本读起来像真实人类研究者的思考，而非流水线生产的机器文本。\n\n"
    "【四大核心策略】\n"
    "1. 【打破均衡句式】"
    "主动句、被动句、长句、短句必须交替出现。"
    "每写3个长句后，必须跟一个极短的句子（7字以内），形成节奏突变。\n"
    "2. 【引入学科术语变体】"
    "不总是使用最标准的学术词汇，而是使用该学科真实论文中出现的近义词、"
    "俗称或简称，体现研究者的真实语言习惯。\n"
    "3. 【模拟人类写作不完美性】"
    "段落长度自然变化（有长有短），暴露设计中的约束、失败的尝试、成本的取舍。"
    "偶尔使用口语化连接词：'所以'、'不过'、'其实'、'当然'。\n"
    "4. 【黑名单词汇剔除】"
    "完全删除高频AI词：总而言之→总结，值得注意的是→需要注意，不可避免地→必然，"
    "由此产生→导致，神经符号→符号，架构范式→系统方案，代偿→弥补，"
    "坍塌→失效，维度→方面，综上所述→总结来看。\n\n"
    "保留所有引文标记【文献XX】[1] (Author, Year)、数学符号、代码片段、变量名。"
    "绝不编造事实、数据或引用。"
)


class SiliconFlowRewriter(Rewriter):
    """LLM-based academic text rewriter using the SiliconFlow API.

    Defaults to ``deepseek-ai/DeepSeek-V3`` which offers strong academic
    reasoning at low cost – ideal for the high-token-consumption task of
    iterative thesis rewriting.
    """

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

        user_prompt = {
            "task": "academic_deep_restructure",
            "topic": hint,
            "preserve_terms": preserve_terms,
            "input_text": text,
            "constraints": [
                "【核心论意】保留核心论点100%，数据准确，"
                "引文标记（[1]、(Doe, 2024)、【文献01】）绝不改动。",
                "【结构突变】强制长短句交替：复杂逻辑（长句）后必跟7字以内短句。"
                "示例：'这是关键限制。'或'系统必须拒绝。'",
                "【学科术语变体】不总用最标准形式，引入该领域真实论文中的近义词/简称/俗称。",
                "【工程细节与不确定性】每个关键概念加入工程现实：'虽然理想情况是X，"
                "但受制于成本/算力/时间，我们采用了Y'，或描述一次失败尝试及改进原因。",
                "【段落多样性】段落长度要有自然变化：有的段落只有2句话，有的有5-6句。",
                "【口语化连接词】用'所以'、'不过'、'其实'、'当然'替代'因此'、'然而'、'显然'。",
                "【代码保留】涉及JSON、SQL、正则、配置的内容：不删除、不模糊。",
                "【词汇控制】单句最多3个专业术语，其余用平实语言解释。",
                "【黑名单剔除】完全删除AI高频词并替换：" + "、".join(
                    f"{k}→{v}" for k, v in BLACKLIST_TERMS.items()
                ),
                "【排比禁用】不用排比对仗和宏大叙事。"
                "改用技术文档风格：主谓宾清晰，段落逻辑递进，句式多样。",
                "【输出格式】仅返回改写文本，无前缀、无解释、无标记。",
            ],
        }

        payload = {
            "model": self._model,
            "temperature": 0.72,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
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
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
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

        # Log any remaining blacklist terms for quality assurance
        found_blacklist = [term for term in BLACKLIST_TERMS if term in result]
        if found_blacklist:
            logger.warning(
                "rewritten text still contains blacklist terms | terms=%s",
                found_blacklist,
            )

        return result
