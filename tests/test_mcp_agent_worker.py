from __future__ import annotations

import unittest

from workers.mcp_agent_worker import build_conversation, build_prompt


class McpAgentWorkerTests(unittest.TestCase):
    def test_build_prompt_uses_request_text_or_legacy_utterances(self) -> None:
        request = {
            "request_id": 1,
            "text": "What is the capital of Netherlands?",
        }
        self.assertEqual(build_prompt(request), "What is the capital of Netherlands?")

        legacy_draft = {
            "request_id": 2,
            "utterances": [
                {"source_line_id": 4, "text": "What is"},
                {"source_line_id": 5, "text": "the capital of China?"},
            ],
        }
        self.assertEqual(build_prompt(legacy_draft), "What is the capital of China?")

    def test_build_conversation_skips_system_notice_and_current_draft(self) -> None:
        snapshot = {
            "events": [
                {"role": "user", "text": "What is the capital of China?", "is_final": True, "kind": "transcript", "source_line_id": 5},
                {"role": "assistant", "text": "Draft 2 queued for external agents.", "is_final": True, "kind": "system_notice", "source_line_id": 5},
                {"role": "assistant", "text": "Beijing.", "is_final": True, "kind": "assistant_reply", "source_line_id": 5},
                {"role": "user", "text": "Is that correct?", "is_final": True, "kind": "transcript", "source_line_id": 6},
            ]
        }
        conversation = build_conversation(snapshot, exclude_source_line_ids={6}, history_events=8)
        self.assertEqual(
            conversation,
            [
                {"role": "user", "text": "What is the capital of China?"},
                {"role": "assistant", "text": "Beijing."},
            ],
        )


if __name__ == "__main__":
    unittest.main()
