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
import re

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
    "你是一名软件工程本科毕业论文的写作助手。"
    "只允许输出严肃、客观、平实、技术化的学术文本，不写口语，不写自媒体语气。\n\n"
    "【四大核心策略】\n"
    "1. 【打破均衡句式】"
    "句长与句法结构要自然错落，但不得刻意制造口语短句。"
    "禁止模板化排比，如'不仅...更...'、'一方面...另一方面...'。\n"
    "2. 【引入学科术语变体】"
    "术语可做有限同义替换，但保持专业准确，优先使用论文常见规范表达。"
    "不得把学术术语降级为网络口语。\n"
    "3. 【模拟工程真实约束】"
    "优先呈现工程阻力与权衡：资源限制、接口异常、参数妥协、误报漏报、性能与成本平衡。"
    "叙述必须具体，避免'完美解决'式线性叙事。\n"
    "4. 【黑名单词汇剔除】"
    "删除高频AI腔词并替换为朴素技术表达，避免宏大叙事和夸张修辞。\n\n"
    "保留所有引文标记【文献XX】[1] (Author, Year)、数学符号、代码片段、变量名。"
    "绝不编造事实、数据或引用。"
    "禁止输出思考过程、策略分点、推理草稿、用户需求复述。"
    "禁止出现'为了规避AI检测'之类元话语。"
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
        model_name: str | None = None,
        enable_reasoning: bool = True,
    ) -> str:
        if not self._api_key:
            return text

        preserve_terms = preserve_terms or []
        hint = topic_hint or "学术论文"
        selected_model = (model_name or self._model).strip() or self._model

        user_prompt = _build_user_prompt(
            text=text,
            hint=hint,
            preserve_terms=preserve_terms,
            strong_restructure=False,
        )

        if not enable_reasoning:
            user_prompt["constraints"].append(
                "【推理模式】关闭。直接输出最终改写结果，不要输出推理过程或步骤说明。"
            )

        payload = {
            "model": selected_model,
            "temperature": 0.68 if enable_reasoning else 0.52,
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

        data = await self._request_completion(payload, headers, timeout, text_len=len(text))
        if data is None:
            return text

        choices = data.get("choices") or []
        if not choices:
            return text

        message = choices[0].get("message", {}) or {}
        content = _extract_message_text(message)
        result = content.strip() or text

        if settings.rewrite_retry_on_low_change and len(text) >= 140:
            change_ratio = _normalized_change_ratio(text, result)
            if change_ratio < settings.rewrite_min_change_ratio:
                logger.info(
                    "rewrite low-change retry triggered | ratio=%.3f | min=%.3f",
                    change_ratio,
                    settings.rewrite_min_change_ratio,
                )
                stronger_prompt = _build_user_prompt(
                    text=text,
                    hint=hint,
                    preserve_terms=preserve_terms,
                    strong_restructure=True,
                )
                stronger_payload = {
                    "model": selected_model,
                    "temperature": 0.62 if enable_reasoning else 0.48,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(stronger_prompt, ensure_ascii=False)},
                    ],
                }
                retry_data = await self._request_completion(stronger_payload, headers, timeout, text_len=len(text))
                if retry_data is not None:
                    retry_choices = retry_data.get("choices") or []
                    if retry_choices:
                        retry_message = retry_choices[0].get("message", {}) or {}
                        retry_content = _extract_message_text(retry_message).strip()
                        if retry_content:
                            result = retry_content

        # Log any remaining blacklist terms for quality assurance
        found_blacklist = [term for term in BLACKLIST_TERMS if term in result]
        if found_blacklist:
            logger.warning(
                "rewritten text still contains blacklist terms | terms=%s",
                found_blacklist,
            )

        return result

    async def _request_completion(
        self,
        payload: dict,
        headers: dict,
        timeout: httpx.Timeout,
        *,
        text_len: int,
    ) -> dict | None:
        max_attempts = max(1, settings.siliconflow_max_retries + 1)
        backoff = max(0.1, settings.siliconflow_retry_backoff_seconds)

        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(1, max_attempts + 1):
                try:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    return resp.json()
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
                    if attempt >= max_attempts:
                        logger.warning(
                            "siliconflow timeout after retries | attempts=%s | text_len=%s | fallback=original",
                            attempt,
                            text_len,
                        )
                        return None
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
                    return None
                except Exception as exc:  # noqa: BLE001
                    if settings.log_exception_stack:
                        logger.exception("siliconflow unknown error | fallback=original | error=%s", exc)
                    else:
                        logger.error("siliconflow unknown error | fallback=original | error=%s", exc)
                    return None


def _extract_message_text(message: dict) -> str:
    """Extract final assistant text while intentionally ignoring reasoning fields."""
    content = message.get("content", "")

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts).strip()

    if isinstance(content, dict):
        text = content.get("text")
        return text.strip() if isinstance(text, str) else ""

    return content.strip() if isinstance(content, str) else ""


def _build_user_prompt(
    *,
    text: str,
    hint: str,
    preserve_terms: list[str],
    strong_restructure: bool,
) -> dict:
    constraints = [
        "【核心论意】保留核心论点100%，数据准确，引文标记（[1]、(Doe, 2024)、【文献01】）绝不改动。",
        "【句法约束】句式可变但必须学术化；禁止口语化词（如'这事儿'、'踏实了'、'其实'）。",
        "【学科术语变体】允许有限术语替换，禁止网络化表达或夸张比喻。",
        "【工程细节与不确定性】优先写约束、报错、退让方案、性能-成本权衡，不得写'完美解决'。",
        "【段落多样性】段落长度自然变化，逻辑清晰递进，不要机械对称。",
        "【结构去模板】禁止'其一/其二/其三'、'首先/其次/最后'、'目的/方法/结论/对策'模板化分段。",
        "【论证去对称】避免正反绝对对称结构，允许论证权重不均，突出关键矛盾与约束条件。",
        "【代码保留】涉及JSON、SQL、正则、配置的内容：不删除、不模糊。",
        "【词汇控制】优先技术事实陈述，少形容词，避免价值判断与煽动性措辞。",
        "【黑名单剔除】完全删除AI高频词并替换：" + "、".join(
            f"{k}→{v}" for k, v in BLACKLIST_TERMS.items()
        ),
        "【排比禁用】禁止排比对仗、宏大叙事、文学化修辞。改用技术文档风格：主谓宾清晰，证据驱动，边界明确。",
        "【事实边界】不得新增具体实验数据、年份、机构统计、平台案例，除非原文已经提供。",
        "【输出格式】仅返回改写文本，无前缀、无解释、无标记。如果你有内部思考，不得展示给用户。",
    ]

    if strong_restructure:
        constraints.append(
            "【强制重构】在不改变事实的前提下，必须重排句序和段内逻辑，避免沿用原文骨架。"
        )

    return {
        "task": "academic_deep_restructure",
        "topic": hint,
        "preserve_terms": preserve_terms,
        "input_text": text,
        "constraints": constraints,
    }


def _normalized_change_ratio(original: str, rewritten: str) -> float:
    if not original:
        return 1.0
    src = re.sub(r"\s+", "", original)
    dst = re.sub(r"\s+", "", rewritten)
    if not src and not dst:
        return 0.0

    same = sum(1 for a, b in zip(src, dst) if a == b)
    max_len = max(len(src), len(dst), 1)
    similarity = same / max_len
    return max(0.0, min(1.0, 1.0 - similarity))
