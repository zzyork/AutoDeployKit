import json
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress

from server_check.main import WEB_CHECK_HANDLERS, inspect_server_web
from utils.ssh_utils import close_ssh_client, ssh_connect
from webui import agent

TERMINAL = {"succeeded", "partial", "failed", "interrupted"}


class JobRunner:
    def __init__(
        self,
        database,
        *,
        connector=ssh_connect,
        inspector=inspect_server_web,
        decide=agent.decide,
        summarize=agent.summarize,
    ):
        self.db = database
        self.connector = connector
        self.inspector = inspector
        self.decide = decide
        self.summarize = summarize
        self.pending = queue.Queue()
        self.subscribers = {}
        self.lock = threading.Lock()
        self.worker = threading.Thread(target=self._work, name="webui-jobs", daemon=True)

    def start(self):
        self.worker.start()

    def stop(self):
        self.pending.put(None)
        self.worker.join(timeout=1)

    def enqueue(self, conversation_id):
        job_id = self.db.create_job(conversation_id, {})
        self.pending.put((job_id, conversation_id))
        self._publish(job_id, "job.queued", {"status": "queued"})
        return job_id

    def _publish(self, job_id, event, data):
        item = {"event": event, "data": data}
        with self.lock:
            for subscriber in self.subscribers.get(job_id, []):
                with suppress(queue.Full):
                    subscriber.put_nowait(item)

    def events(self, job_id):
        subscriber = queue.Queue(maxsize=100)
        with self.lock:
            snapshot = self.db.get_job(job_id)
            if snapshot is None:
                raise ValueError("Unknown job")
            self.subscribers.setdefault(job_id, []).append(subscriber)
        try:
            yield self._frame("job.snapshot", snapshot)
            if snapshot["status"] in TERMINAL:
                return
            while True:
                try:
                    item = subscriber.get(timeout=15)
                except queue.Empty:
                    current = self.db.get_job(job_id)
                    if current is None or current["status"] in TERMINAL:
                        yield self._frame("job.completed", {"status": current["status"] if current else "failed"})
                        return
                    yield ": heartbeat\n\n"
                    continue
                yield self._frame(item["event"], item["data"])
                if item["event"] == "job.completed":
                    return
        finally:
            with self.lock:
                self.subscribers[job_id].remove(subscriber)
                if not self.subscribers[job_id]:
                    del self.subscribers[job_id]

    @staticmethod
    def _frame(event, data):
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _work(self):
        while True:
            entry = self.pending.get()
            if entry is None:
                return
            job_id, conversation_id = entry
            try:
                self._process(job_id, conversation_id)
            except Exception:  # noqa: BLE001 - Keep remote/provider failures out of responses and logs.
                try:
                    self.db.update_job(job_id, "failed", error="任务失败")
                except Exception:  # noqa: BLE001 - Even a DB failure must not kill the worker.
                    pass
                finally:
                    self._publish(job_id, "job.completed", {"status": "failed"})

    def _process(self, job_id, conversation_id):
        self.db.update_job(job_id, "running")
        self._publish(job_id, "job.started", {"status": "running"})
        messages = self.db.get_messages(conversation_id)
        credentials = self.db.model_credentials()
        name, arguments = self.decide(messages, credentials)
        if name is None:
            self.db.add_message(conversation_id, "assistant", arguments["message"])
            self.db.update_job(
                job_id, "succeeded", result={"hosts": [], "message": arguments["message"]}
            )
            self._publish(job_id, "assistant.message", {"content": arguments["message"]})
            self._publish(job_id, "job.completed", {"status": "succeeded"})
            return
        hosts = self.db.resolve_hosts(arguments["host_pattern"])
        self.db.update_job(job_id, "running", tool_name=name)
        if name == "latest_inspection":
            names = {host["name"] for host in hosts}
            reports = [report for report in self.db.list_reports() if report["host"] in names]
            selected = reports[:1]
            results = {"hosts": [], "reports": selected}
            status = "succeeded"
        elif name == "inspect_servers":
            checks = arguments.get("checks")
            if checks is not None and (
                not checks
                or len(checks) > len(WEB_CHECK_HANDLERS)
                or len(set(checks)) != len(checks)
                or any(check not in WEB_CHECK_HANDLERS for check in checks)
            ):
                raise ValueError("未知巡检项")
            results = {"hosts": []}
            self.db.update_job(job_id, "running", result=results)
            with ThreadPoolExecutor(max_workers=min(5, len(hosts))) as executor:
                futures = {
                    executor.submit(self._inspect_host, job_id, host, checks): host
                    for host in hosts
                }
                for future in as_completed(futures):
                    outcome = future.result()
                    results["hosts"].append(outcome)
                    self.db.update_job(job_id, "running", result=results)
            successes = sum(host["status"] == "succeeded" for host in results["hosts"])
            status = (
                "succeeded" if successes == len(hosts) else "partial" if successes else "failed"
            )
        else:
            raise ValueError("未开放的工具")
        safe_result = {
            "status": status,
            "succeeded": sum(item["status"] == "succeeded" for item in results["hosts"]),
            "failed": sum(item["status"] == "failed" for item in results["hosts"]),
            "risk_count": sum(item["risk_count"] for item in results["hosts"]),
            "report_ids": [item["report_id"] for item in results["hosts"] if item.get("report_id")]
            + [item["id"] for item in results.get("reports", [])],
        }
        try:
            reply = self.summarize(messages, credentials, name, safe_result)
        except Exception:  # noqa: BLE001 - A successful inspection result remains queryable.
            reply = "任务已完成，请查看任务与报告。"
        self.db.add_message(conversation_id, "assistant", reply)
        self._publish(job_id, "assistant.message", {"content": reply})
        self.db.update_job(job_id, status, result=results)
        self._publish(job_id, "job.completed", {"status": status})

    def _inspect_host(self, job_id, host, checks):
        self._publish(job_id, "host.connecting", {"host": host["name"]})
        client = None
        try:
            client = self.connector(**self.db.connection_settings(host["id"]))
            client._web_deadline = time.monotonic() + 120
            self._publish(job_id, "host.inspecting", {"host": host["name"]})
            outcome = self.inspector(
                host["name"], client, self.db.report_root, uuid.uuid4().hex, checks
            )
            result = {
                "host": host["name"],
                "status": outcome["status"],
                "risk_count": len(outcome["alerts"]),
                "report_id": outcome["report_id"],
                "error": outcome["error"],
            }
        except Exception:  # noqa: BLE001 - A failed host must not abort the other hosts.
            result = {
                "host": host["name"],
                "status": "failed",
                "risk_count": 0,
                "report_id": None,
                "error": "连接或巡检失败",
            }
        finally:
            if client is not None:
                close_ssh_client(client)
        self._publish(
            job_id, "host.succeeded" if result["status"] == "succeeded" else "host.failed", result
        )
        return result
