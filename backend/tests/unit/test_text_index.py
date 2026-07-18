from app.services.text_index import clean_text, search_terms


def test_search_terms_generates_han_bigrams_and_word_tokens() -> None:
    assert search_terms("深度学习 GPT-4") == "深度 度学 学习 gpt 4"


def test_clean_text_preserves_paragraph_lines() -> None:
    assert clean_text("  first   line \n\n second\tline ") == "first line\nsecond line"
