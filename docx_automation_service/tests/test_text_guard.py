from docx_automation_service.services.text_guard import (
    check_entity_hallucination,
    is_heading_like,
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
