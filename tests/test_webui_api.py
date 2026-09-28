import json
import queue
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from webui import agent
from webui.agent import decide
from webui.app import create_app
from webui.jobs import JobRunner
from webui.security import create_key_file
from webui.storage import Database


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        key_path = root / "master.key"
        create_key_file(key_path)
        self.db = Database(root / "data", key_path)
        self.db.initialize()
        self.db.set_admin_password("long-example-passphrase")
        self.db.set_model_settings("https://model.example/v1", "demo", "api-secret")

        def fake_inspector(host, _client, report_root, report_id, _checks):
            report = Path(report_root) / f"{report_id}.md"
            report.write_text("Private report for " + host, encoding="utf-8")
            if host == "broken":
                report.unlink()
                return {"status": "failed", "alerts": [], "report_id": None, "error": "巡检失败"}
            return {
                "status": "succeeded",
                "alerts": ["risk"],
                "report_id": report_id,
                "error": None,
            }

        self.runner = JobRunner(
            self.db,
            connector=lambda **_kwargs: MagicMock(),
            inspector=fake_inspector,
            decide=lambda *_args: (
                "inspect_servers",
                {"host_pattern": "sample", "checks": ["server_info"]},
            ),
            summarize=lambda *_args: "发现一台主机需要关注。",
        )
        self.client = TestClient(create_app(database=self.db, runner=self.runner))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def login(self):
        result = self.client.post("/api/login", json={"password": "long-example-passphrase"})
        self.assertEqual(result.status_code, 200)
        return {"X-CSRF-Token": result.json()["csrf_token"]}

    def test_auth_csrf_and_asset_response_never_return_password(self):
        self.assertEqual(self.client.get("/api/hosts").status_code, 401)
        headers = self.login()
        payload = {
            "name": "demo",
            "address": "demo.invalid",
            "username": "operator",
            "password": "ssh-secret",
            "group_name": "sample",
        }
        self.assertEqual(self.client.post("/api/hosts", json=payload).status_code, 403)
        result = self.client.post("/api/hosts", json=payload, headers=headers)
        self.assertEqual(result.status_code, 201)
        self.assertNotIn("ssh-secret", result.text)
        self.assertTrue(result.json()["has_password"])
        self.assertNotIn("api-secret", self.client.get("/api/settings").text)

    def test_chat_partial_completion_and_report_by_id(self):
        headers = self.login()
        for name in ("healthy", "broken"):
            response = self.client.post(
                "/api/hosts",
                json={
                    "name": name,
                    "address": name + ".invalid",
                    "username": "operator",
                    "password": "secret",
                    "group_name": "sample",
                },
                headers=headers,
            )
            self.assertEqual(response.status_code, 201)
        start = self.client.post("/api/chat", json={"message": "巡检 sample"}, headers=headers)
        self.assertEqual(start.status_code, 202)
        job_id = start.json()["job_id"]
        for _ in range(100):
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("succeeded", "partial", "failed"):
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "partial")
        reports = self.client.get("/api/reports").json()
        self.assertEqual(len(reports), 1)
        self.assertIn("Private report", self.client.get("/api/reports/" + reports[0]["id"]).text)
        self.assertEqual(self.client.get("/api/reports/../outside").status_code, 404)
        self.assertIn("job.snapshot", self.client.get(f"/api/jobs/{job_id}/events").text)

    def test_unknown_model_tool_is_rejected(self):
        response = MagicMock()
        model_answer = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "run_shell",
                                    "arguments": '{"command":"rm -rf /"}',
                                }
                            }
                        ]
                    }
                }
            ]
        }
        response.iter_content.return_value = [json.dumps(model_answer).encode("utf-8")]
        with (
            patch("webui.agent.requests.post", return_value=response) as post,
            self.assertRaisesRegex(ValueError, "未开放"),
        ):
            decide([{"role": "user", "content": "test"}], self.db.model_credentials())
        self.assertTrue(post.call_args.kwargs["stream"])
        response.close.assert_called_once()

    def test_trickling_model_response_has_a_total_deadline(self):
        response = MagicMock()
        response.iter_content.return_value = [b"{", b" "]
        with (
            patch("webui.agent.requests.post", return_value=response),
            patch.object(agent.time, "monotonic", side_effect=[0, 1, 61]),
            self.assertRaises(TimeoutError),
        ):
            decide([{"role": "user", "content": "test"}], self.db.model_credentials())
        response.close.assert_called_once()

    def test_worker_publishes_terminal_event_even_if_failure_record_cannot_be_written(self):
        database = MagicMock()
        database.update_job.side_effect = OSError("database unavailable")
        runner = JobRunner(database)
        runner._publish = MagicMock()
        runner.pending.put(("job-id", "conversation-id"))
        runner.pending.put(None)
        runner._work()
        runner._publish.assert_called_once_with("job-id", "job.completed", {"status": "failed"})

    def test_event_subscription_recovers_persisted_terminal_state(self):
        conversation_id = self.db.create_conversation("demo")
        job_id = self.db.create_job(conversation_id, {})
        self.db.update_job(job_id, "running")
        events = self.runner.events(job_id)
        self.assertIn("job.snapshot", next(events))
        self.db.update_job(job_id, "failed", error="任务失败")
        subscriber = self.runner.subscribers[job_id][0]
        with patch.object(subscriber, "get", side_effect=queue.Empty):
            self.assertIn('"status": "failed"', next(events))
        events.close()

    def test_duplicate_checks_never_open_ssh(self):
        headers = self.login()
        self.client.post(
            "/api/hosts",
            json={"name": "demo", "address": "demo.invalid", "username": "operator", "password": "secret", "group_name": "sample"},
            headers=headers,
        )
        self.runner.decide = lambda *_args: ("inspect_servers", {"host_pattern": "sample", "checks": ["server_info", "server_info"]})
        self.runner.connector = MagicMock()
        job_id = self.client.post("/api/chat", json={"message": "巡检 sample"}, headers=headers).json()["job_id"]
        for _ in range(100):
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] == "failed":
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "failed")
        self.runner.connector.assert_not_called()

    def test_password_change_revokes_existing_session(self):
        headers = self.login()
        self.assertEqual(
            self.client.patch("/api/settings", json={"admin_password": "wrong", "new_password": "new-long-passphrase"}, headers=headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch("/api/settings", json={"admin_password": "long-example-passphrase", "new_password": "new-long-passphrase"}, headers=headers).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/hosts").status_code, 401)
        self.assertTrue(self.db.verify_admin("new-long-passphrase"))


if __name__ == "__main__":
    unittest.main()
