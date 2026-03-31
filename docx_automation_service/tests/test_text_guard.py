from docx_automation_service.services.text_guard import is_heading_like, sanitize_model_output, split_for_rewrite


def test_sanitize_removes_think_block() -> None:
    raw = "<think>这里是模型思考</think>\n最终正文内容[1]"
    cleaned = sanitize_model_output(raw, original_text="原文", source_is_heading=False)
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
    cleaned = sanitize_model_output(raw, original_text="原文", source_is_heading=False)
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
