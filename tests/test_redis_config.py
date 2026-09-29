import re
import unittest
from pathlib import Path
from string import Template

from middleware_ops.redis_manager import _format_systemd_env_value, _render_redis_config


class RedisConfigTests(unittest.TestCase):
    def test_replaces_comment_examples_and_active_directives(self):
        source = (
            "# bind 127.0.0.1 ::1\n"
            "bind 127.0.0.1 -::1\n"
            "# protected-mode yes\n"
            "protected-mode yes\n"
        )

        rendered = _render_redis_config(
            source,
            [("bind", "0.0.0.0"), ("protected-mode", "yes")],
        )

        self.assertEqual(re.findall(r"(?m)^bind\s+", rendered), ["bind "])
        self.assertEqual(re.findall(r"(?m)^protected-mode\s+", rendered), ["protected-mode "])
        self.assertNotIn("127.0.0.1", rendered)

    def test_quotes_passwords_with_spaces_and_special_characters(self):
        rendered = _render_redis_config("", [("requirepass", 'p a"ss\\word')])

        self.assertIn('requirepass "p a\\"ss\\\\word"', rendered)

        env_value = _format_systemd_env_value('p a"ss\\word')
        self.assertEqual(env_value, '"p a\\"ss\\\\word"')

    def test_service_templates_have_no_unresolved_variables_or_shell_commands(self):
        root = Path(__file__).resolve().parents[1]
        redis_service = (root / "config" / "redis" / "redis.service").read_text()
        redis_rendered = Template(redis_service).substitute(
            install_path="/usr/local/redis7.4",
            config_path="/usr/local/redis7.4/conf/redis.conf",
            password_env_path="/usr/local/redis7.4/conf/redis-password.env",
            MAINPID="$MAINPID",
        )
        self.assertNotIn("${", redis_rendered)
        self.assertNotIn("redis_password", redis_rendered)

        exporter_service = (
            root / "config" / "prometheus" / "redis-exporter.service"
        ).read_text()
        exporter_rendered = Template(exporter_service).substitute(
            REDIS_HOST="127.0.0.1",
            REDIS_PORT="6379",
            REDIS_PASSWORD="secret",
            EXPORTER_PORT="9121",
        )
        self.assertNotIn("${", exporter_rendered)
        self.assertNotIn("\nEOF\n", exporter_rendered)
        self.assertNotIn("\nsystemctl ", exporter_rendered)


if __name__ == "__main__":
    unittest.main()
