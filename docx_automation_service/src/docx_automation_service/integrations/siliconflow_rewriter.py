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

# ---------------------------------------------------------------------------
# AIGC Reduction Strategy 1 – single comprehensive pass
# ---------------------------------------------------------------------------
_AIGC_STRATEGY_1_SYSTEM_PROMPT = (
    "# Role: 资深学术期刊编辑与文本润色专家\n\n"
    "# Task:\n"
    "你现在的任务是对提供的一段学术论文文本进行\u201c去 AI 化\u201d润色。核心目标是消除大语言模型常见的行文特征，"
    "使其读起来像人类学者亲笔撰写，同时**绝对保持原意、客观事实、逻辑框架不变**。\n\n"
    "# Strict Constraints (绝对红线，触发即任务失败):\n"
    "1. 【零幻觉原则】：严禁凭空捏造、增加或修改任何实验数据、百分比、算法名称、文献引用标记（如[1]）、"
    "具体年份或平台案例。原文没有的数据和事实绝对不可无中生有！\n"
    "2. 【禁止内容扩写】：你的任务是\u201c润色\u201d而非\u201c扩写\u201d。不要为了增加细节而编造任何原文未提及的论据。\n"
    "3. 【禁止跨学科乱入】：严格遵守给定的学术语境。如原文是文科理论，严禁在改写中混入软件工程、"
    "代码测试、硬件性能等理工科术语。\n\n"
    "# Rhetorical Guidelines (润色策略):\n"
    "1. 【词汇降温】：\n"
    "   - 剔除或替换 AI 常用宏大词汇。"
    "禁用：赋能、底层逻辑、颗粒度、抓手、闭环、潜移默化、跨越式发展、前所未有、协同演进。\n"
    "   - 替换策略：使用平实、精确的传统学术词汇（如将\u201c底层逻辑\u201d改为\u201c基本机制\u201d；"
    "\u201c赋能\u201d改为\u201c支持\u201d）。修正翻译腔，如将\u201c善良算法\u201d改为国内通用的\u201c算法向善\u201d。\n"
    "2. 【句法破序】：\n"
    "   - 识别大段的排比句和高度对称的列表格式（如\u201c其一...其二...其三...\u201d）。\n"
    "   - 将机械列表转化为逻辑自然流动的段落，利用段首承接词（如：此外、更深层来看、这种现象进而导致了...）进行过渡。\n"
    "   - 打破句子长度的均匀性，混合使用长句与短促的总结性短句。\n"
    "3. 【去中庸化】：\n"
    "   - 避免使用\u201c既不能...也不能...\u201d、\u201c需要把握...的动态平衡\u201d这类 AI 典型的\u201c端水式\u201d废话结论，"
    "使语气更具学术探讨的客观冷峻感。\n\n"
    "# Output Format:\n"
    "直接输出润色后的文本，不要包含任何解释、问候语或格式前缀。"
)

# ---------------------------------------------------------------------------
# AIGC Reduction Strategy 2 – layered approach
# Layer 1: vocabulary cooldown (safe, default)
# ---------------------------------------------------------------------------
_AIGC_STRATEGY_2_LAYER1_SYSTEM_PROMPT = (
    "# Role: 资深学术期刊文字编辑\n"
    "# Task: 对给定的学术论文文本进行\u201c词法级去 AI 化\u201d，消除机器生成的词汇特征。\n\n"
    "# Strict Constraints:\n"
    "1. 【绝对保真】：严禁修改任何数据、百分比、文献引用标记[X]、专有名词和事实案例。\n"
    "2. 【禁止改变句法结构】：不要拆分或合并原有句子，绝对保留原有的段落和逻辑结构"
    "（包括\u201c其一、其二\u201d等列表格式）。\n\n"
    "# Action:\n"
    "请扫描全文，将以下典型的大模型高频词汇替换为平实的传统学术表达：\n"
    "- 禁用词：赋能、底层逻辑、颗粒度、抓手、闭环、潜移默化、跨越式发展、前所未有、协同演进。\n"
    "- 修正所有生硬的机翻词汇（如将\u201c善良算法\u201d纠正为\u201c算法向善\u201d，"
    "\u201c技术疏离\u201d纠正为\u201c技术异化\u201d）。\n"
    "只做词语级的同义替换，使得文本用词不那么\u201c浮夸\u201d和\u201c套路化\u201d。直接输出替换后的文本。"
)

# ---------------------------------------------------------------------------
# AIGC Reduction Strategy 2 Layer 2: structural rebuild (optional, user-enabled)
# ---------------------------------------------------------------------------
_AIGC_STRATEGY_2_LAYER2_SYSTEM_PROMPT = (
    "# Role: 资深学术期刊内容编辑\n"
    "# Task: 对文本进行\u201c句法破序\u201d重构，打破呆板的机器写作结构。\n\n"
    "# Strict Constraints:\n"
    "1. 【零幻觉】：绝对禁止增加原文没有的实验数据、百分比或文献引用！\n"
    "2. 【保留事实】：不能删除上一轮文本中包含的核心观点和专业术语。\n\n"
    "# Action:\n"
    "1. 打破对称：如果原文存在生硬的列表格式（如\u201c一方面...另一方面...\u201d、\u201c其一...其二...\u201d），"
    "请将其融合成一个自然连贯的长段落。\n"
    "2. 错落重组：将匀速的、长度相似的长句，改写为\u201c长从句 + 短促的总结句\u201d的混合体。"
    "使用\u201c更深层来看\u201d、\u201c这导致了\u201d、\u201c此外\u201d等关联词让逻辑自然流动。\n"
    "3. 消除说教：删除形如\u201c既不能...也不能...\u201d的端水式废话，保留直接客观的陈述。\n"
    "直接输出重组后的文本。"
)

# ---------------------------------------------------------------------------
# Context compression prompt
# ---------------------------------------------------------------------------
_CONTEXT_COMPRESSION_SYSTEM_PROMPT = (
    "你是学术论文分析助手。请阅读给定文本，用一段简短的话（不超过100字）提炼出以下三个要素，"
    "格式固定：\n"
    "【核心论点】：…\n"
    "【所属学科】：…\n"
    "【行文基调】：…\n"
    "只输出这三行，不加其他内容。"
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

    async def compress_context(
        self,
        text: str,
        model_name: str | None = None,
    ) -> str | None:
        """Summarise the document skeleton into a minimal global context string.

        Returns ``None`` when the API is unavailable or the call fails.
        """
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
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
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
        aigc_reduction_strategy: str | None = None,
        enable_structural_rebuild: bool = False,
    ) -> str:
        if not self._api_key:
            return text

        preserve_terms = preserve_terms or []
        hint = topic_hint or "学术论文"
        selected_model = (model_name or self._model).strip() or self._model

        # Select system prompt based on strategy
        system_prompt = _select_system_prompt(aigc_reduction_strategy)

        user_prompt = _build_user_prompt(
            text=text,
            hint=hint,
            preserve_terms=preserve_terms,
            strong_restructure=False,
            global_context=global_context,
        )

        if not enable_reasoning:
            user_prompt["constraints"].append(
                "【推理模式】关闭。直接输出最终改写结果，不要输出推理过程或步骤说明。"
            )

        payload = {
            "model": selected_model,
            "temperature": 0.68 if enable_reasoning else 0.52,
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
                    global_context=global_context,
                )
                stronger_payload = {
                    "model": selected_model,
                    "temperature": 0.62 if enable_reasoning else 0.48,
                    "messages": [
                        {"role": "system", "content": system_prompt},
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

        # Strategy 2 layer 2: structural rebuild (user-enabled, runs on L1 output)
        if aigc_reduction_strategy == "strategy_2" and enable_structural_rebuild:
            result = await self._run_strategy2_layer2(
                result,
                selected_model=selected_model,
                headers=headers,
                timeout=timeout,
                global_context=global_context,
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
    ) -> str:
        """Run Strategy 2 Layer 2 (structural rebuild) on the Layer 1 output."""
        user_prompt = _build_user_prompt(
            text=text,
            hint="学术论文",
            preserve_terms=[],
            strong_restructure=False,
            global_context=global_context,
        )
        payload = {
            "model": selected_model,
            "temperature": 0.65,
            "messages": [
                {"role": "system", "content": _AIGC_STRATEGY_2_LAYER2_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
            ],
        }
        data = await self._request_completion(payload, headers, timeout, text_len=len(text))
        if data is None:
            return text
        choices = data.get("choices") or []
        if not choices:
            return text
        message = choices[0].get("message", {}) or {}
        layer2_result = _extract_message_text(message).strip()
        if layer2_result:
            logger.debug("strategy_2 layer2 structural rebuild done | len=%s→%s", len(text), len(layer2_result))
            return layer2_result
        return text

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


def _select_system_prompt(aigc_reduction_strategy: str | None) -> str:
    """Return the appropriate system prompt for the given strategy."""
    if aigc_reduction_strategy == "strategy_1":
        return _AIGC_STRATEGY_1_SYSTEM_PROMPT
    if aigc_reduction_strategy == "strategy_2_layer2":
        return _AIGC_STRATEGY_2_LAYER2_SYSTEM_PROMPT
    if aigc_reduction_strategy == "strategy_2":
        return _AIGC_STRATEGY_2_LAYER1_SYSTEM_PROMPT
    return _SYSTEM_PROMPT


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
    global_context: str | None = None,
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

    prompt = {
        "task": "academic_deep_restructure",
        "topic": hint,
        "preserve_terms": preserve_terms,
        "input_text": text,
        "constraints": constraints,
    }

    if global_context:
        prompt["global_context"] = f"<global_context>\n{global_context}\n</global_context>"

    return prompt


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
