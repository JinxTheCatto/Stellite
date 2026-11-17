import tempfile
import unittest
from types import SimpleNamespace

from run_logging import ManualKeyLogger, SessionLog, format_skipped_key


class SessionLogTests(unittest.TestCase):
    def test_formats_skipped_chart_key_with_lateness(self):
        message = format_skipped_key("d", 0.064, clock=lambda: 123.5)

        self.assertEqual(message, "123.5: Skipped chart key D (scheduler was 64 ms late)")

    def test_writes_plain_text_messages_to_a_txt_file(self):
        with tempfile.TemporaryDirectory() as directory:
            session_log = SessionLog(directory)
            try:
                session_log.write("\x1b[31mLost sync with the highway\x1b[0m")
                content = session_log.path.read_text(encoding="utf-8")

                self.assertEqual(session_log.path.suffix, ".txt")
                self.assertIn("Stellite session started:", content)
                self.assertIn("Lost sync with the highway", content)
                self.assertNotIn("\x1b", content)
            finally:
                session_log.close()

    def test_logs_each_manual_key_press_once_until_release(self):
        messages = []
        logger = ManualKeyLogger(
            ["d", "space"],
            lambda: True,
            messages.append,
            clock=lambda: 123.5,
        )

        logger.handle(SimpleNamespace(name="d", event_type="down"))
        logger.handle(SimpleNamespace(name="d", event_type="down"))
        logger.handle(SimpleNamespace(name="d", event_type="up"))
        logger.handle(SimpleNamespace(name="d", event_type="down"))

        self.assertEqual(messages, [
            "123.5: Manual key press D",
            "123.5: Manual key press D",
        ])

    def test_ignores_keys_outside_manual_mode(self):
        messages = []
        logger = ManualKeyLogger(["d"], lambda: False, messages.append)

        logger.handle(SimpleNamespace(name="d", event_type="down"))

        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
