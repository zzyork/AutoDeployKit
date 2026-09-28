import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from server_check import docker, error_logs, main, monitors
from utils import ssh_utils
from utils.output import print_error


class WebInspectionTests(unittest.TestCase):
    def test_web_report_uses_only_report_id_and_keeps_output_private(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "reports"
            log_path = Path(directory) / "output.log"
            client = MagicMock()
            client._web_mode = True

            def sample_check(_client, filename, _config, alerts):
                Path(filename).write_text("## sample\n", encoding="utf-8")
                alerts.append("warning")

            with (
                patch.object(main, "run_command", return_value=("../../outside", "", 0)),
                patch.dict(main.WEB_CHECK_HANDLERS, {"sample": sample_check}, clear=True),
                patch("utils.output.LOG_FILE", str(log_path)),
            ):
                result = main.inspect_server_web("asset-1", client, root, "a" * 32, ["sample"])

            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(Path(result["report_path"]), root / ("a" * 32 + ".md"))
            self.assertIn("sample", (root / ("a" * 32 + ".md")).read_text(encoding="utf-8"))
            self.assertFalse(log_path.exists())

    def test_web_report_id_rejects_traversal_before_ssh(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(main, "run_command") as run,
            self.assertRaises(ValueError),
        ):
            main.inspect_server_web("asset-1", MagicMock(), Path(directory), "../bad")
        run.assert_not_called()

    def test_logged_handler_error_is_a_failed_web_result_without_secret_logging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "reports"
            log_path = Path(directory) / "output.log"
            with (
                patch.object(main, "run_command", return_value=("demo", "", 0)),
                patch.dict(
                    main.WEB_CHECK_HANDLERS,
                    {"sample": lambda *_: print_error("secret remote error")},
                    clear=True,
                ),
                patch("utils.output.LOG_FILE", str(log_path)),
            ):
                result = main.inspect_server_web("asset", MagicMock(), root, "c" * 32, ["sample"])
            self.assertEqual(result["status"], "failed")
            self.assertFalse(log_path.exists())
            self.assertFalse((root / ("c" * 32 + ".md")).exists())

    def test_report_creation_collision_does_not_erase_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_id = "b" * 32
            final = root / f"{report_id}.md"
            original_open = main.os.open

            def race(path, flags, mode=0o777):
                if Path(path) == final:
                    final.write_text("previous report", encoding="utf-8")
                    raise FileExistsError("report exists")
                return original_open(path, flags, mode)

            with (
                patch.object(main, "run_command", return_value=("demo", "", 0)),
                patch.dict(main.WEB_CHECK_HANDLERS, {"sample": lambda *_: None}, clear=True),
                patch.object(main.os, "open", side_effect=race),
            ):
                result = main.inspect_server_web("asset", MagicMock(), root, report_id, ["sample"])
            self.assertEqual(result["status"], "failed")
            self.assertEqual(final.read_text(encoding="utf-8"), "previous report")

    def test_web_docker_does_not_switch_context(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "body"
            client = MagicMock()
            client._web_mode = True
            with patch.object(docker, "run_command", return_value=("", "", 0)) as run:
                docker.docker_status(client, str(filename), {}, [])
            commands = [args.args[1] for args in run.call_args_list]
            self.assertNotIn("docker context use default 2>&1", commands)
            self.assertTrue(any("docker --context default ps" in cmd for cmd in commands))

    def test_cli_run_keeps_existing_directory_choice_and_arguments(self):
        clients = [("example", MagicMock())]
        with (
            patch.object(main, "choose_report_path", return_value="custom-reports") as choose,
            patch.object(main, "load_config", return_value={"checks": []}),
            patch.object(main, "inspect_server") as inspect,
            patch.object(main, "print_info"),
        ):
            main.run(clients)
            choose.assert_called_once_with("server_check/reporters")
            inspect.assert_called_once_with(
                "example", clients[0][1], "custom-reports", {"checks": []}
            )

    def test_remote_exporter_name_cannot_add_a_command(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "body"
            output = ("node-exporter.service\nnode-exporter.service;touch /tmp/unsafe", "", 0)
            with patch.object(
                monitors, "run_command", side_effect=[output, ("active", "", 0)]
            ) as run:
                monitors.monitors(MagicMock(), str(filename), {}, [])
            self.assertEqual(run.call_count, 2)
            self.assertNotIn("touch", run.call_args.args[1])

    def test_web_logs_do_not_use_login_shell(self):
        client = MagicMock()
        client._web_mode = True
        with patch.object(error_logs, "run_command", return_value=("", "", 0)) as run:
            error_logs._collect_journal_errors(client, 30, 200)
            error_logs._collect_file_errors(client, "/var/log/messages", 200)
        self.assertTrue(all(args.args[1].startswith("bash -c ") for args in run.call_args_list))

    def test_web_ssh_uses_only_selected_memory_key(self):
        with patch.object(ssh_utils.paramiko, "SSHClient") as factory:
            client = factory.return_value
            pkey = MagicMock()
            result = ssh_utils.ssh_connect("example.invalid", "operator", pkey=pkey, web=True)
            self.assertIs(result, client)
            kwargs = client.connect.call_args.kwargs
            self.assertEqual(kwargs["pkey"], pkey)
            self.assertFalse(kwargs["allow_agent"])
            self.assertFalse(kwargs["look_for_keys"])
            self.assertNotIn("password", kwargs)
            self.assertEqual(ssh_utils._build_remote_command(client, "hostname"), "hostname")

    def test_web_ssh_proxy_failure_closes_opened_proxy(self):
        with patch.object(ssh_utils.paramiko, "SSHClient") as factory:
            target, proxy = MagicMock(), MagicMock()
            factory.side_effect = [target, proxy]
            proxy.get_transport.return_value = None
            with self.assertRaises(RuntimeError):
                ssh_utils.ssh_connect(
                    "target",
                    "operator",
                    password="secret",
                    proxy="jump",
                    proxy_user="operator",
                    proxy_password="other",
                    web=True,
                )
            self.assertTrue(proxy.close.called)

    def test_web_command_deadline_closes_channel(self):
        client = MagicMock()
        client._web_mode = True
        channel = client.get_transport.return_value.open_session.return_value
        channel.recv_ready.return_value = False
        channel.recv_stderr_ready.return_value = False
        channel.exit_status_ready.return_value = False
        with (
            patch.object(ssh_utils.time, "monotonic", side_effect=[0, 0, 21]),
            patch.object(ssh_utils.time, "sleep"),
            self.assertRaises(TimeoutError),
        ):
            ssh_utils.run_command(client, "hostname")
        channel.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
