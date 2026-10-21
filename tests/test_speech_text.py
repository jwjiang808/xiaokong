from __future__ import annotations

from xiaokong.speech.text import SentenceSplitter, clean_for_speech


def stream_chunks(text: str, step: int = 3) -> list[str]:
    splitter = SentenceSplitter()
    out: list[str] = []
    for i in range(0, len(text), step):
        out.extend(splitter.push(text[i : i + step]))
    out.extend(splitter.flush())
    return out


def test_markdown_and_code_are_not_spoken() -> None:
    reply = (
        "你好！这是一个测试。\n\n"
        "## 小标题\n"
        "- 第一点内容，需要朗读出来。\n"
        "- 第二点带有 `代码` 和 **重点**。\n\n"
        "```python\nprint('这段代码不应该被朗读')\n```\n\n"
        "结束。"
    )
    chunks = stream_chunks(reply)
    joined = "".join(chunks)

    assert "print" not in joined
    assert "```" not in joined
    assert "**" not in joined and "`" not in joined
    assert joined.count("第一点") == 1


def test_first_sentence_emitted_before_reply_completes() -> None:
    splitter = SentenceSplitter()
    assert splitter.push("你好") == []
    assert splitter.push("！后面还有很多字") == ["你好！"]


def test_long_text_without_punctuation_is_split() -> None:
    splitter = SentenceSplitter()
    pieces = splitter.push("一" * 200)
    pieces.extend(splitter.flush())

    assert all(len(piece) <= 70 for piece in pieces)
    assert sum(len(piece) for piece in pieces) == 200


def test_urls_and_images_are_removed() -> None:
    cleaned = clean_for_speech("看这里 https://example.com/a/b 以及 ![图](x.png) 完")
    assert "http" not in cleaned and "png" not in cleaned
