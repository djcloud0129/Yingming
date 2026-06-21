from __future__ import annotations

import unittest

from yingming_core.llm import LLMError, friendly_llm_error


class LLMErrorTests(unittest.TestCase):
    def test_ssl_eof_error_is_user_readable(self) -> None:
        message = friendly_llm_error(
            LLMError("无法连接模型接口：[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
        )

        self.assertIn("SSL", message)
        self.assertIn("网络", message)
        self.assertNotIn("UNEXPECTED_EOF_WHILE_READING", message)

    def test_unauthorized_error_mentions_api_key(self) -> None:
        message = friendly_llm_error(LLMError("模型接口返回错误：HTTP 401 Unauthorized"))

        self.assertIn("API Key", message)


if __name__ == "__main__":
    unittest.main()
