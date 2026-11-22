"""Docker's env_file keeps a trailing "# comment" as part of the value; settings must not."""
from __future__ import annotations

from app.core.config import Settings


def test_comment_only_value_is_empty():
    s = Settings(openai_base_url="# e.g. http://host.docker.internal:11434/v1 for a local Ollama")
    assert s.openai_base_url in (None, "")


def test_trailing_comment_is_dropped():
    s = Settings(llm_model="gpt-5.4-nano   # cheapest", llm_max_output_tokens="3000  # lower for free tiers")
    assert s.llm_model == "gpt-5.4-nano" and s.llm_max_output_tokens == 3000


def test_hash_inside_a_value_is_kept():
    s = Settings(llm_model="model#v2")
    assert s.llm_model == "model#v2"


def test_comment_only_number_uses_the_default():
    assert Settings(llm_max_output_tokens="# set per provider").llm_max_output_tokens == 8000
