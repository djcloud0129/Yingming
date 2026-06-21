from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.request import Request
import ssl

from yingming_core.llm import LLMError, OfflineYingming, OpenAICompatibleClient, friendly_llm_error
from yingming_core.settings import ModelSettings


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

    def test_urllib_ssl_failure_falls_back_to_curl(self) -> None:
        client = OpenAICompatibleClient(settings=ModelSettings(api_key="test-key"))
        request = Request("https://example.test/chat/completions", data=b"{}")

        with (
            patch("yingming_core.llm.urlopen", side_effect=ssl.SSLError("boom")),
            patch.object(client, "_complete_with_curl", return_value={"choices": []}) as curl_fallback,
        ):
            data = client._complete_with_urllib(request)

        self.assertEqual(data, {"choices": []})
        curl_fallback.assert_called_once_with(request)

    def test_offline_default_reply_does_not_repeat_local_mode(self) -> None:
        reply = OfflineYingming().complete([{"role": "user", "content": "现在是这样的"}])

        self.assertNotIn("本地备用", reply)
        self.assertNotIn("离线模式", reply)


if __name__ == "__main__":
    unittest.main()
