from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.conversation_service import ConversationService
from app.response_writer import ResponseWriter
from app.transcript_store import TranscriptStore


class ConversationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = TranscriptStore(
            persistence_path=Path(self.tempdir.name) / "transcript_history.json",
            history_limit=10,
        )
        self.service = ConversationService(
            store=self.store,
            response_writer=ResponseWriter(self.store),
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _complete_line(self, line_id: int, text: str) -> None:
        self.store.upsert_line(
            event_type="line_completed",
            line_id=line_id,
            text=text,
            start_time=0.0,
            duration=1.0,
            is_complete=True,
            speaker_index=0,
            latency_ms=0,
        )

    def test_completed_lines_group_into_one_pending_draft(self) -> None:
        self._complete_line(1, "What is")
        self._complete_line(2, "the capital of China?")

        snapshot = self.store.snapshot()
        utterances = snapshot["utterances"]

        self.assertEqual(len(utterances), 2)
        self.assertEqual({utterance["draft_id"] for utterance in utterances}, {1})
        self.assertTrue(all(utterance["status"] == "pending" for utterance in utterances))

    def test_queue_and_complete_draft_updates_timeline(self) -> None:
        self._complete_line(1, "What is")
        self._complete_line(2, "the capital of China?")

        queue_result = asyncio.run(self.service.queue_draft(1))
        self.assertTrue(queue_result["queued"])

        claim_result = asyncio.run(self.service.claim_draft(1, agent_name="chatgpt", agent_label="ChatGPT"))
        self.assertTrue(claim_result["claimed"])

        complete_result = asyncio.run(
            self.service.complete_draft(1, agent_name="chatgpt", agent_label="ChatGPT", text="Beijing.")
        )
        self.assertTrue(complete_result["completed"])

        snapshot = self.store.snapshot()
        utterances = snapshot["utterances"]
        self.assertTrue(all(utterance["status"] == "completed" for utterance in utterances))
        self.assertTrue(all(utterance["agent_name"] == "chatgpt" for utterance in utterances))
        self.assertTrue(all(utterance["agent_label"] == "ChatGPT" for utterance in utterances))
        self.assertTrue(all(utterance["request_id"] == 1 for utterance in utterances))

        assistant_events = [event for event in snapshot["events"] if event["role"] == "assistant"]
        self.assertEqual(assistant_events[-1]["text"], "Beijing.")
        self.assertEqual(assistant_events[-1]["agent_name"], "ChatGPT")

        request_events = snapshot["request_events"]
        self.assertEqual(
            [event["kind"] for event in request_events],
            ["request_created", "request_updated", "request_queued", "agent_claimed", "agent_completed"],
        )
        self.assertTrue(all(event["request_id"] == 1 for event in request_events))

        agent_statuses = snapshot["agent_statuses"]
        self.assertEqual(agent_statuses[-1]["name"], "chatgpt")
        self.assertEqual(agent_statuses[-1]["status"], "ready")

    def test_fail_draft_marks_utterances_failed(self) -> None:
        self._complete_line(1, "Check this")

        asyncio.run(self.service.queue_draft(1))
        asyncio.run(self.service.claim_draft(1, agent_name="claude", agent_label="Claude"))
        fail_result = asyncio.run(
            self.service.fail_draft(1, agent_name="claude", agent_label="Claude", error="Claude could not verify the claim.")
        )

        self.assertTrue(fail_result["failed"])
        snapshot = self.store.snapshot()
        utterance = snapshot["utterances"][0]
        self.assertEqual(utterance["status"], "failed")
        self.assertEqual(utterance["agent_label"], "Claude")
        self.assertEqual(utterance["error"], "Claude could not verify the claim.")
        self.assertEqual(snapshot["request_events"][-1]["kind"], "agent_failed")

    def test_delegate_request_creates_child_request(self) -> None:
        self._complete_line(1, "What is the capital of Netherlands?")

        result = asyncio.run(
            self.service.delegate_request(
                1,
                target_agent_name="claude",
                target_agent_label="Claude",
            )
        )

        self.assertTrue(result["delegated"])
        snapshot = self.store.snapshot()
        self.assertEqual(len(snapshot["requests"]), 2)
        child = next(request for request in snapshot["requests"] if request["request_id"] == 2)
        self.assertEqual(child["parent_request_id"], 1)
        self.assertEqual(child["target_agent_name"], "claude")
        self.assertEqual(child["status"], "queued")
        self.assertEqual(snapshot["request_events"][-1]["kind"], "subrequest_queued")

    def test_targeted_child_request_can_only_be_claimed_by_target_agent(self) -> None:
        self._complete_line(1, "Check this statement")
        asyncio.run(
            self.service.delegate_request(
                1,
                target_agent_name="claude",
                target_agent_label="Claude",
            )
        )

        wrong_claim = asyncio.run(self.service.claim_draft(2, agent_name="chatgpt", agent_label="ChatGPT"))
        self.assertFalse(wrong_claim["claimed"])
        self.assertIn("delegated to Claude", wrong_claim["reason"])

        right_claim = asyncio.run(self.service.claim_draft(2, agent_name="claude", agent_label="Claude"))
        self.assertTrue(right_claim["claimed"])

    def test_clear_preserves_agent_statuses(self) -> None:
        self.store.set_agent_status(name="chatgpt", status="ready", label="ChatGPT", detail="Connected")
        self._complete_line(1, "Hello there")

        snapshot = self.store.clear()

        self.assertEqual(snapshot["lines"], [])
        self.assertEqual(snapshot["events"], [])
        self.assertEqual(snapshot["utterances"], [])
        self.assertEqual(snapshot["request_events"], [])
        self.assertEqual(len(snapshot["agent_statuses"]), 1)
        self.assertEqual(snapshot["agent_statuses"][0]["name"], "chatgpt")
        self.assertEqual(snapshot["agent_statuses"][0]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
