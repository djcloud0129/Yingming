from __future__ import annotations

import unittest

from yingming_core.memory_retrieval import (
    format_memory_context,
    format_retrieved_memories,
    retrieve_relevant_memories,
)


class MemoryRetrievalTests(unittest.TestCase):
    def test_retrieves_relevant_confirmed_memory(self) -> None:
        data = {
            "long_term": [
                {
                    "id": "mem_movie",
                    "category": "preference",
                    "text": "用户喜欢聊科幻电影《降临》和《银翼杀手2049》。",
                    "source": "test",
                },
                {
                    "id": "mem_mcu",
                    "category": "learning",
                    "text": "用户正在学习单片机和嵌入式基础。",
                    "source": "test",
                },
            ],
            "pending": [],
            "boundaries": [],
        }

        results = retrieve_relevant_memories(data, "我们继续聊《降临》吧")

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].id, "mem_movie")

    def test_ignores_pending_memories(self) -> None:
        data = {
            "long_term": [],
            "pending": [
                {
                    "id": "pend_secret",
                    "category": "manual",
                    "text": "这条还没有被确认。",
                    "source": "test",
                }
            ],
            "boundaries": [],
        }

        results = retrieve_relevant_memories(data, "这条还没有被确认")

        self.assertEqual(results, [])

    def test_recall_query_returns_broad_memories(self) -> None:
        data = {
            "long_term": [
                {"id": "mem_project", "category": "project", "text": "用户在做樱茗项目。"},
                {"id": "mem_identity", "category": "identity", "text": "用户叫云玦。"},
            ],
            "pending": [],
            "boundaries": [],
        }

        results = retrieve_relevant_memories(data, "你记得我什么？")

        self.assertEqual([item.id for item in results[:2]], ["mem_identity", "mem_project"])

    def test_format_memory_context_includes_only_retrieved_long_term(self) -> None:
        data = {
            "owner": {"preferred_language": "中文为主"},
            "long_term": [
                {"id": "mem_movie", "category": "preference", "text": "用户喜欢《降临》。"},
                {"id": "mem_game", "category": "preference", "text": "用户喜欢 Apex。"},
            ],
            "pending": [{"id": "pend_1", "category": "manual", "text": "待确认内容。"}],
            "boundaries": ["不要把待确认记忆当作事实。"],
        }
        retrieved = retrieve_relevant_memories(data, "聊聊降临")

        context = format_memory_context(data, retrieved)
        readable = format_retrieved_memories(retrieved)

        self.assertIn("中文为主", context)
        self.assertIn("用户喜欢《降临》。", context)
        self.assertNotIn("用户喜欢 Apex。", context)
        self.assertNotIn("待确认内容。", context)
        self.assertIn("当前相关长期记忆", readable)


if __name__ == "__main__":
    unittest.main()
