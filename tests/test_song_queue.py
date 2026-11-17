import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import charts


class SongQueuePromptTests(unittest.TestCase):
    def test_ignores_other_keys_until_yes(self):
        output = io.StringIO()
        with patch.object(charts.msvcrt, "getwch", side_effect=["x", "\r", "y"]):
            with redirect_stdout(output):
                result = charts.prompt_queue_another()

        self.assertTrue(result)
        self.assertIn("Queue another song? (Y/N)", output.getvalue())

    def test_no_declines_queue(self):
        with patch.object(charts.msvcrt, "getwch", return_value="n"):
            with redirect_stdout(io.StringIO()):
                self.assertFalse(charts.prompt_queue_another("Queue finished? (Y/N)"))


if __name__ == "__main__":
    unittest.main()
