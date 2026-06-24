import unittest

from cordcloud_checkin.browser_flow import normalize_numeric_code, text_indicates_checkin_success


class BrowserFlowTest(unittest.TestCase):
    def test_normalize_numeric_code_keeps_only_digits(self):
        self.assertEqual(normalize_numeric_code(" 12-34 56 "), "123456")

    def test_text_indicates_checkin_success_accepts_traffic_message(self):
        self.assertTrue(text_indicates_checkin_success("获得了 315MB 流量."))

    def test_text_indicates_checkin_success_accepts_already_checked_in(self):
        self.assertTrue(text_indicates_checkin_success("已签到"))

    def test_text_indicates_checkin_success_rejects_empty_or_unknown_text(self):
        self.assertFalse(text_indicates_checkin_success(""))
        self.assertFalse(text_indicates_checkin_success("签到结果未知"))


if __name__ == "__main__":
    unittest.main()
