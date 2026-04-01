"""Layer 2 – Semantic Deep Restructuring via LLM rewriting."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from docx_automation_service.core.config import settings
from docx_automation_service.integrations.base import Rewriter
from docx_automation_service.services.text_guard import count_guard_tokens

logger = logging.getLogger(__name__)

_PROMPT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "assets" / "prompts" / "aigc_reduction.json"

BLACKLIST_TERMS: dict[str, str] = {
    "总而言之": "总结",
    "值得注意的是": "需要注意",
    "不可避免地": "往往会",
    "由此产生的": "这会带来",
    "神经符号": "符号推理",
    "架构": "系统结构",
    "代偿": "弥补",
    "坍塌": "失效",
    "隔离层": "拦截层",
    "维度": "方面",
    "范式": "方案",
    "伦理约束": "规则约束",
    "综上所述": "综合来看",
    "不言而喻": "可以看出",
    "多维度": "多方面",
}

_DEFAULT_SYSTEM_PROMPT = (
    "你是一名软件工程本科毕业论文的写作助手。只允许输出严肃、客观、平实、技术化的学术文本，不写口语。\n"
    "【句式扰动｜打破均衡句式】强制长短句交替，打断对称式/八股文式结构，避免连续完美长句。\n"
    "【人类瑕疵与口语化微调】在陈述过渡可使用“事实上”“需要注意的是”“然而实际上”等自然衔接词，"
    "但保持学术语气，避免套话。\n"
    "【绝对红线】绝对禁止修改任何专业术语语义；绝对禁止改变标题层级或标题名称（如“结论”不得改写）；"
    "不确定词一律保持原样。\n"
    "【事实边界】绝不编造事实、数据、年份、引用；保留所有引用标记、变量名、代码片段、占位符。\n"
    "【结构去模板】禁止“其一/其二/其三”“首先/其次/最后”模板化分段。"
)
_DEFAULT_STRATEGY_1_SYSTEM_PROMPT = _DEFAULT_SYSTEM_PROMPT + "\n【策略】单轮高保真人类化重写。"
_DEFAULT_STRATEGY_2_LAYER1_SYSTEM_PROMPT = (
    _DEFAULT_SYSTEM_PROMPT + "\n【策略】第一层仅做词法降温与节奏调整，不改变段落逻辑框架。"
)
_DEFAULT_STRATEGY_2_LAYER2_SYSTEM_PROMPT = (
    _DEFAULT_SYSTEM_PROMPT + "\n【策略】第二层做句法破序与结构重排，但核心事实与术语绝不改变。"
)

_CONTEXT_COMPRESSION_SYSTEM_PROMPT = (
    "你是学术论文分析助手。请阅读给定文本，用一段简短的话（不超过100字）提炼出以下三个要素，格式固定：\n"
    "【核心论点】：…\n【所属学科】：…\n【行文基调】：…\n只输出这三行，不加其他内容。"
)

def _load_prompt_templates() -> dict[str, str]:
    templates = {
        "default": _DEFAULT_SYSTEM_PROMPT,
        "strategy_1": _DEFAULT_STRATEGY_1_SYSTEM_PROMPT,
        "strategy_2_layer1": _DEFAULT_STRATEGY_2_LAYER1_SYSTEM_PROMPT,
        "strategy_2_layer2": _DEFAULT_STRATEGY_2_LAYER2_SYSTEM_PROMPT,
    }
    try:
        if _PROMPT_CONFIG_PATH.exists():
            data = json.loads(_PROMPT_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in templates:
                    value = data.get(key)
                    if isinstance(value, str) and value.strip():
                        templates[key] = value
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed loading prompt config json | path=%s | error=%s", _PROMPT_CONFIG_PATH, exc)
    return templates

_PROMPT_TEMPLATES = _load_prompt_templates()
_SYSTEM_PROMPT = _PROMPT_TEMPLATES["default"]
_AIGC_STRATEGY_1_SYSTEM_PROMPT = _PROMPT_TEMPLATES["strategy_1"]
_AIGC_STRATEGY_2_LAYER1_SYSTEM_PROMPT = _PROMPT_TEMPLATES["strategy_2_layer1"]
_AIGC_STRATEGY_2_LAYER2_SYSTEM_PROMPT = _PROMPT_TEMPLATES["strategy_2_layer2"]

_GUARD_TOKEN_RE = re.compile(r"\[\[GUARD_TOKEN_\d{3}\]\]")
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_NON_CJK_ALPHA_RE = re.compile(r"[A-Za-z]")

class SiliconFlowRewriter(Rewriter):
    def __init__(self) -> None:
        self._base_url = settings.siliconflow_base_url.rstrip("/")
        self._api_key = settings.siliconflow_api_key
        self._model = settings.siliconflow_model

    async def compress_context(self, text: str, model_name: str | None = None) -> str | None:
        if not self._api_key:
            return None

        selected_model = (model_name or self._model).strip() or self._model
        payload = {
            "model": selected_model,
            "temperature": 0.3,
            "max_tokens": 200,
            "messages": [
                {"role": "system", "content": _CONTEXT_COMPRESSION_SYSTEM_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        data = await self._request_completion(payload, headers, timeout, text_len=len(text))
        if data is None:
            return None
        choices = data.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message", {}) or {}
        result = _extract_message_text(message).strip()
        return result or None

    async def rewrite(
        self,
        text: str,
        topic_hint: str | None = None,
        preserve_terms: list[str] | None = None,
        model_name: str | None = None,
        enable_reasoning: bool = True,
        global_context: str | None = None,
        previous_context: str | None = None,
        aigc_reduction_strategy: str | None = None,
        enable_structural_rebuild: bool = False,
    ) -> str:
        if not self._api_key:
            return text

        preserve_terms = preserve_terms or []
        hint = topic_hint or "学术论文"
        selected_model = (model_name or self._model).strip() or self._model
        system_prompt = _select_system_prompt(aigc_reduction_strategy)

        user_prompt = _build_user_prompt(
            text=text,
            hint=hint,
            preserve_terms=preserve_terms,
            strong_restructure=False,
            global_context=global_context,
            previous_context=previous_context,
        )
        if not enable_reasoning:
            user_prompt["constraints"].append("【推理模式】关闭。直接输出最终改写结果，不输出推理过程。")

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        timeout = httpx.Timeout(
            connect=min(15.0, settings.siliconflow_timeout_seconds),
            read=settings.siliconflow_timeout_seconds,
            write=30.0,
            pool=30.0,
        )

        result = await self._request_validated_rewrite(
            selected_model=selected_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            headers=headers,
            timeout=timeout,
            source_text=text,
            temperature=0.68 if enable_reasoning else 0.52,
        )

        if settings.rewrite_retry_on_low_change and len(text) >= 140:
            change_ratio = _normalized_change_ratio(text, result)
            if change_ratio < settings.rewrite_min_change_ratio:
                stronger_prompt = _build_user_prompt(
                    text=text,
                    hint=hint,
                    preserve_terms=preserve_terms,
                    strong_restructure=True,
                    global_context=global_context,
                    previous_context=previous_context,
                )
                stronger_result = await self._request_validated_rewrite(
                    selected_model=selected_model,
                    system_prompt=system_prompt,
                    user_prompt=stronger_prompt,
                    headers=headers,
                    timeout=timeout,
                    source_text=text,
                    temperature=0.62 if enable_reasoning else 0.48,
                )
                result = stronger_result or result

        if aigc_reduction_strategy == "strategy_2" and enable_structural_rebuild:
            result = await self._run_strategy2_layer2(
                result,
                selected_model=selected_model,
                headers=headers,
                timeout=timeout,
                global_context=global_context,
                previous_context=previous_context,
            )

        return result

    async def _run_strategy2_layer2(
        self,
        text: str,
        *,
        selected_model: str,
        headers: dict,
        timeout: httpx.Timeout,
        global_context: str | None,
        previous_context: str | None,
    ) -> str:
        user_prompt = _build_user_prompt(
            text=text,
            hint="学术论文",
            preserve_terms=[],
            strong_restructure=True,
            global_context=global_context,
            previous_context=previous_context,
        )
        result = await self._request_validated_rewrite(
            selected_model=selected_model,
            system_prompt=_AIGC_STRATEGY_2_LAYER2_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            headers=headers,
            timeout=timeout,
            source_text=text,
            temperature=0.65,
        )
        return result or text

    async def _request_validated_rewrite(
        self,
        *,
        selected_model: str,
        system_prompt: str,
        user_prompt: dict[str, Any],
        headers: dict[str, str],
        timeout: httpx.Timeout,
        source_text: str,
        temperature: float,
        max_validation_retries: int = 2,
    ) -> str:
        prompt = copy.deepcopy(user_prompt)

        for attempt in range(1, max_validation_retries + 2):
            payload = {
                "model": selected_model,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
            }
            data = await self._request_completion(payload, headers, timeout, text_len=len(source_text))
            if data is None:
                return source_text

            choices = data.get("choices") or []
            if not choices:
                return source_text

            message = choices[0].get("message", {}) or {}
            candidate = _extract_message_text(message).strip() or source_text
            invalid_reason = _validate_rewrite_output(source_text, candidate)
            if invalid_reason is None:
                return candidate

            if attempt >= max_validation_retries + 1:
                return source_text

            prompt.setdefault("constraints", [])
            prompt["constraints"].append(
                f"【校验修正】上一版失败原因：{invalid_reason}。必须保留所有GUARD_TOKEN且以中文输出。"
            )

        return source_text

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
                    resp = await client.post(f"{self._base_url}/chat/completions", headers=headers, json=payload)
                    resp.raise_for_status()
                    return resp.json()
                except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.PoolTimeout):
                    if attempt >= max_attempts:
                        return None
                    await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code in {408, 429, 500, 502, 503, 504} and attempt < max_attempts:
                        await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                        continue
                    return None
                except Exception:
                    return None

def _select_system_prompt(aigc_reduction_strategy: str | None) -> str:
    if aigc_reduction_strategy == "strategy_1":
        return _AIGC_STRATEGY_1_SYSTEM_PROMPT
    if aigc_reduction_strategy == "strategy_2_layer2":
        return _AIGC_STRATEGY_2_LAYER2_SYSTEM_PROMPT
    if aigc_reduction_strategy == "strategy_2":
        return _AIGC_STRATEGY_2_LAYER1_SYSTEM_PROMPT
    return _SYSTEM_PROMPT

def _extract_message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
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
    global_context: str | None = None,
    previous_context: str | None = None,
) -> dict:
    constraints = [
        "【核心论意】保留核心论点100%，数据准确，引文标记绝不改动。",
        "【句式扰动】必须长短句交替，避免连续对称长句与模板化八股结构。",
        "【人类化衔接】可自然使用“事实上”“需要注意的是”“然而实际上”等过渡。",
        "【绝对红线】绝不改变术语语义；绝不改标题层级与标题名（例如“结论”保持原样）。",
        "【术语保留】不确定术语保持原样，不得替换为近义但失真的词。",
        "【结构去模板】禁止'其一/其二/其三'、'首先/其次/最后'、'目的/方法/结论/对策'模板化分段。",
        "【代码保留】涉及JSON、SQL、正则、配置、变量名的内容：不删除、不模糊。",
        "【事实边界】不得新增具体实验数据、年份、机构统计、平台案例，除非原文已提供。",
        "【黑名单剔除】优先替换AI高频词：" + "、".join(f"{k}→{v}" for k, v in BLACKLIST_TERMS.items()),
        "【输出格式】仅返回改写文本，无前缀、无解释、无标记。",
    ]
    if strong_restructure:
        constraints.append("【强制重构】在不改变事实的前提下重排句序，避免沿用原骨架。")

    prompt = {
        "task": "academic_deep_restructure",
        "topic": hint,
        "preserve_terms": preserve_terms,
        "input_text": text,
        "constraints": constraints,
    }
    if global_context:
        prompt["global_context"] = f"<global_context>\n{global_context}\n</global_context>"
    if previous_context:
        prompt["previous_context"] = (
            f"这是上一段的结尾：{previous_context}。请承接它的语气和逻辑重写当前段落，但输出只包含当前段落重写后的内容。"
        )
    return prompt

def _validate_rewrite_output(source_text: str, rewritten_text: str) -> str | None:
    if not rewritten_text.strip():
        return "empty_output"

    source_tokens = count_guard_tokens(source_text)
    output_tokens = count_guard_tokens(rewritten_text)
    if source_tokens != output_tokens:
        return f"guard_token_mismatch({source_tokens}!={output_tokens})"

    source_len = len(source_text.strip())
    output_len = len(rewritten_text.strip())
    if source_len > 0 and output_len < max(1, int(source_len * 0.3)):
        return f"too_short({output_len}/{source_len})"

    normalized = _GUARD_TOKEN_RE.sub("", rewritten_text)
    cjk_count = len(_CJK_CHAR_RE.findall(normalized))
    non_cjk_alpha_count = len(_NON_CJK_ALPHA_RE.findall(normalized))
    total_letters = cjk_count + non_cjk_alpha_count
    if total_letters > 0:
        ratio = non_cjk_alpha_count / total_letters
        if ratio > 0.10:
            return f"non_zh_ratio_high({ratio:.3f})"

    return None

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