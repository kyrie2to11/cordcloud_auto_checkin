import email
import unittest
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

from cordcloud_checkin.mail import (
    extract_code_from_message,
    extract_message_bodies,
    extract_verification_code,
    message_is_before,
)


class MailParsingTest(unittest.TestCase):
    def test_extract_verification_code_prefers_six_digit_code(self):
        code, desc = extract_verification_code("您的验证码为 123456，请勿泄露。")

        self.assertEqual(code, "123456")
        self.assertEqual(desc, "6位数字紧邻验证码")

    def test_extract_verification_code_supports_code_label(self):
        code, desc = extract_verification_code("Your code: 654321")

        self.assertEqual(code, "654321")
        self.assertEqual(desc, "6位数字紧邻code")

    def test_extract_message_bodies_reads_plain_and_html_parts(self):
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("plain 验证码为 111222", "plain", "utf-8"))
        msg.attach(MIMEText("<p>html 验证码为 333444</p>", "html", "utf-8"))

        plain_body, full_body = extract_message_bodies(msg)

        self.assertIn("plain 验证码为 111222", plain_body)
        self.assertIn("html 验证码为 333444", full_body)

    def test_extract_code_from_message_prefers_plain_text_over_html(self):
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText("验证码为 111222", "plain", "utf-8"))
        msg.attach(MIMEText("<p>验证码为 333444</p>", "html", "utf-8"))

        code, desc, source, body = extract_code_from_message(msg)

        self.assertEqual(code, "111222")
        self.assertEqual(source, "纯文本")
        self.assertIn("111222", body)

    def test_message_is_before_filters_old_messages(self):
        msg = email.message_from_string(
            "Subject: test\n"
            f"Date: {formatdate(1000, usegmt=True)}\n"
            "\n"
            "验证码为 123456"
        )

        self.assertTrue(message_is_before(msg, 2000))
        self.assertFalse(message_is_before(msg, 500))


if __name__ == "__main__":
    unittest.main()
