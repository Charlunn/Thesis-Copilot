from docx_automation_service.services.text_guard import (
    GuardContext,
    check_entity_hallucination,
    is_heading_like,
    is_references_section,
    sanitize_model_output,
    split_for_rewrite,
)


def test_sanitize_removes_think_block() -> None:
    raw = "<think>这里是模型思考</think>\n最终正文内容[1]"
    # original_text must contain [1] so the entity-hallucination guard does not fire and
    # "最终正文内容[1]" is returned rather than falling back to original_text.
    cleaned = sanitize_model_output(raw, original_text="源文内容[1]", source_is_heading=False)
    assert "模型思考" not in cleaned
    assert "最终正文内容" in cleaned


def test_sanitize_removes_reasoning_lines() -> None:
    raw = "我现在需要帮用户改写文本。\n首先，分析策略。\n信息技术发展推动了攻击链条演化。"
    cleaned = sanitize_model_output(raw, original_text="原文", source_is_heading=False)
    assert "我现在需要" not in cleaned
    assert "信息技术发展" in cleaned


def test_sanitize_drops_heading_pollution_for_non_heading_source() -> None:
    raw = "第1章 绪论\n1.1 研究背景与意义\n这是一段正文内容。"
    cleaned = sanitize_model_output(raw, original_text="原文", source_is_heading=False)
    assert "第1章" not in cleaned
    assert "研究背景" not in cleaned
    assert "正文内容" in cleaned


def test_sanitize_drops_strategy_reasoning_block() -> None:
    raw = (
        "第1章 绪论\n"
        "1.1 研究背景与意义\n"
        "第三个策略是模拟人类写作的不完美性，这意味着段落长度要有自然的变化。\n"
        "第四个策略是剔除黑名单词汇。\n"
        "我还需要注意段落长度的变化。\n"
        "随着信息技术的快速发展，电信网络诈骗在全球范围内的破坏力持续增强[06]。"
    )
    # original_text must contain [06] so the citation is not flagged as hallucination
    cleaned = sanitize_model_output(
        raw,
        original_text="随着信息技术的快速发展，电信网络诈骗破坏力持续增强[06]。",
        source_is_heading=False,
    )
    assert "第三个策略" not in cleaned
    assert "第四个策略" not in cleaned
    assert "我还需要注意" not in cleaned
    assert "绪论" not in cleaned
    assert "破坏力持续增强" in cleaned


def test_is_heading_like_supports_style_and_numbering() -> None:
    assert is_heading_like("1.2 研究方法")
    assert is_heading_like("任意文本", "Heading 2")
    assert not is_heading_like("这是普通段落内容", "Normal")


def test_split_for_rewrite_respects_max_chars() -> None:
    text = "。".join(["这是一个较长句子用于切分测试" for _ in range(20)]) + "。"
    chunks = split_for_rewrite(text, target_chars=80, max_chars=120)
    assert len(chunks) > 1
    assert all(len(c) <= 120 for c in chunks)


# ---------------------------------------------------------------------------
# Entity hallucination detection tests
# ---------------------------------------------------------------------------

def test_check_entity_hallucination_no_hallucination() -> None:
    """Text that adds no new numbers/citations is not flagged."""
    source = "信息茧房理论由桑斯坦提出，描述了用户的内容偏好固化现象。"
    generated = "信息茧房概念源于桑斯坦的理论研究，指用户获取信息的渠道逐渐单一化的现象。"
    assert check_entity_hallucination(generated, source) is False


def test_check_entity_hallucination_detects_fabricated_percentage() -> None:
    """A percentage in generated text that is absent from source is flagged."""
    source = "该算法在实验中表现良好。"
    generated = "该算法的准确率达到95.3%，表现优越。"
    assert check_entity_hallucination(generated, source) is True


def test_check_entity_hallucination_detects_fabricated_citation() -> None:
    """A bracket citation in generated text absent from source is flagged."""
    source = "平台推荐机制可能强化用户偏见。"
    generated = "平台推荐机制可能强化用户偏见[1]。"
    assert check_entity_hallucination(generated, source) is True


def test_check_entity_hallucination_detects_author_year_citation() -> None:
    """An author-year citation in generated text absent from source is flagged."""
    source = "过滤泡效应的研究可追溯至早期互联网时代。"
    generated = "过滤泡效应的研究可追溯至早期互联网时代 (Pariser, 2011)。"
    assert check_entity_hallucination(generated, source) is True


def test_check_entity_hallucination_allows_present_numbers() -> None:
    """Numbers already in the source do not trigger the guard."""
    source = "系统准确率为95.3%，召回率为88.7%。"
    generated = "实验结果显示，准确率维持在95.3%的水平，召回率为88.7%。"
    assert check_entity_hallucination(generated, source) is False


def test_sanitize_model_output_falls_back_on_hallucination() -> None:
    """sanitize_model_output returns original_text when hallucination is detected."""
    source = "信息茧房由桑斯坦提出，用于描述媒体偏好固化现象。"
    # Generated text introduces a percentage and a citation absent from source
    generated = "信息茧房由桑斯坦提出，研究表明固化率高达78.5%，详见[2]。"
    result = sanitize_model_output(generated, original_text=source, source_is_heading=False)
    assert result == source


# ---------------------------------------------------------------------------
# GuardContext tests
# ---------------------------------------------------------------------------

def test_guard_context_protects_xml_tags() -> None:
    ctx = GuardContext()
    text = "请<role>管理员</role>审核该功能。"
    protected, token_map = ctx.protect(text)
    assert "<role>" not in protected
    assert len(token_map) == 1
    restored = ctx.restore(protected, token_map)
    assert restored == text


def test_guard_context_protects_bracket_citations() -> None:
    ctx = GuardContext()
    text = "研究表明[1]，该方法有效[2,3]。"
    protected, token_map = ctx.protect(text)
    assert "[1]" not in protected
    assert "[2,3]" not in protected
    restored = ctx.restore(protected, token_map)
    assert restored == text


def test_guard_context_protects_author_year_citations() -> None:
    ctx = GuardContext()
    text = "信息茧房由 Sunstein (2001) 提出。"
    protected, token_map = ctx.protect(text)
    # The author name and/or year should be tokenised (pattern may capture as one or two tokens)
    assert "(2001)" not in protected and "Sunstein" not in protected
    restored = ctx.restore(protected, token_map)
    assert restored == text


def test_guard_context_protects_english_names() -> None:
    ctx = GuardContext()
    text = "该研究由 John Smith 和 Mary Johnson 共同完成。"
    protected, token_map = ctx.protect(text)
    assert "John Smith" not in protected
    assert "Mary Johnson" not in protected
    restored = ctx.restore(protected, token_map)
    assert restored == text


def test_guard_context_protects_years() -> None:
    ctx = GuardContext()
    text = "该算法于2021年发布，并在2023年得到改进。"
    protected, token_map = ctx.protect(text)
    assert "2021" not in protected
    assert "2023" not in protected
    restored = ctx.restore(protected, token_map)
    assert restored == text


def test_guard_context_restore_is_lossless() -> None:
    ctx = GuardContext()
    text = (
        "根据 Smith (2020) 的研究[1]，<role>用户</role>在2022年的参与度提升了。"
    )
    protected, token_map = ctx.protect(text)
    restored = ctx.restore(protected, token_map)
    assert restored == text


def test_guard_context_count_tokens() -> None:
    ctx = GuardContext()
    text = "参见[1]和[2]。"
    protected, token_map = ctx.protect(text)
    assert ctx.count_tokens(protected, token_map) == len(token_map)
    # Simulate a model dropping one token
    one_dropped = protected.replace(list(token_map.keys())[0], "")
    assert ctx.count_tokens(one_dropped, token_map) == len(token_map) - 1


def test_is_references_section_detects_chinese_header() -> None:
    assert is_references_section("参考文献\n[1] Doe, J. 2024.") is True


def test_is_references_section_detects_english_header() -> None:
    assert is_references_section("References\n[1] Smith, A. (2020).") is True


def test_is_references_section_false_for_body_text() -> None:
    assert is_references_section("本文的研究方法采用了定量分析。") is False


def test_is_references_section_false_for_empty_text() -> None:
    assert is_references_section("") is False


# ---------------------------------------------------------------------------
# validate_rewrite_output tests
# ---------------------------------------------------------------------------

from docx_automation_service.integrations.siliconflow_rewriter import validate_rewrite_output


def test_validate_rewrite_output_passes_valid_chinese() -> None:
    original = "这是一段学术论文的正文内容，讨论了相关研究方法和实验设计。"
    output = "此段学术文本涉及研究方法与实验设计的阐述，内容符合学术规范。"
    valid, reason = validate_rewrite_output(output, original)
    assert valid is True
    assert reason == ""


def test_validate_rewrite_output_detects_language_leak() -> None:
    original = "这是一段中文学术论文内容。"
    # Mostly English output – language leak
    output = "This is an English paragraph that replaced the Chinese text completely."
    valid, reason = validate_rewrite_output(output, original)
    assert valid is False
    assert "language_leak" in reason


def test_validate_rewrite_output_detects_length_truncation() -> None:
    original = "这是一段较长的学术论文内容" * 10  # 120+ chars
    output = "太短了。"
    valid, reason = validate_rewrite_output(output, original)
    assert valid is False
    assert "length_truncated" in reason


def test_validate_rewrite_output_detects_guard_token_loss() -> None:
    original = "研究表明[1]效果显著。"
    token_map = {"[[GUARD_TOKEN_000]]": "[1]"}
    # Output is missing the guard token
    output = "研究表明效果显著。"
    valid, reason = validate_rewrite_output(output, original, token_map)
    assert valid is False
    assert "guard_token_loss" in reason


def test_validate_rewrite_output_passes_with_guard_tokens_present() -> None:
    original = "研究表明[1]效果显著。"
    token_map = {"[[GUARD_TOKEN_000]]": "[1]"}
    output = "研究结果表明[[GUARD_TOKEN_000]]效果显著。"
    valid, reason = validate_rewrite_output(output, original, token_map)
    assert valid is True
    assert reason == ""
