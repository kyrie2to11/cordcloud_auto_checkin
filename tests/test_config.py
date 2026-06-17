import os
import unittest
from unittest.mock import patch

from cordcloud_checkin.config import env_bool, env_int, env_value, load_settings


class ConfigTest(unittest.TestCase):
    def test_env_value_treats_empty_string_as_unset(self):
        with patch.dict(os.environ, {"EXAMPLE_KEY": ""}, clear=False):
            self.assertEqual(env_value("EXAMPLE_KEY", "fallback"), "fallback")

    def test_env_bool_and_int(self):
        with patch.dict(os.environ, {"BOOL_KEY": "false", "INT_KEY": "42"}, clear=False):
            self.assertFalse(env_bool("BOOL_KEY", True))
            self.assertEqual(env_int("INT_KEY", 1), 42)

    def test_load_settings_uses_cordcloud_email_as_mail_username_default(self):
        env = {
            "CORDCLOUD_EMAIL": "user@example.com",
            "CORDCLOUD_PASSWORD": "secret",
            "POP3_HOST": "",
            "POP3_PORT": "",
            "POP3_USERNAME": "",
            "SMTP_USERNAME": "",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_settings()

        self.assertEqual(settings.pop3_host, "pop.example.com")
        self.assertEqual(settings.pop3_port, 995)
        self.assertEqual(settings.pop3_username, "user@example.com")
        self.assertEqual(settings.smtp_username, "user@example.com")
        self.assertEqual(settings.pop3_scan_limit, 10)


if __name__ == "__main__":
    unittest.main()
