import unittest

from cordcloud_checkin.browser_flow import normalize_numeric_code


class BrowserFlowTest(unittest.TestCase):
    def test_normalize_numeric_code_keeps_only_digits(self):
        self.assertEqual(normalize_numeric_code(" 12-34 56 "), "123456")


if __name__ == "__main__":
    unittest.main()
