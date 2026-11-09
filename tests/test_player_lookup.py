import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class RequestException(Exception):
    pass


class PlayerLookupTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "utils.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "getPlayerForBsId"
        )
        self.requests = SimpleNamespace(get=Mock(), RequestException=RequestException)
        self.logger = Mock(spec=logging.Logger)
        namespace = {
            "requests": self.requests,
            "envData": {"BsApi": "test-secret"},
            "logger": self.logger,
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        self.lookup = namespace["getPlayerForBsId"]

    def respond(self, status, payload):
        self.requests.get.return_value = SimpleNamespace(
            status_code=status, json=Mock(return_value=payload)
        )

    def test_success_normalizes_tag(self):
        player = {"tag": "#RLJP2JCR", "highestTrophies": 1000, "3vs3Victories": 100}
        self.respond(200, player)
        self.assertEqual(self.lookup(" #rljp2jcr "), (player, "RLJP2JCR", False))
        self.assertEqual(
            self.requests.get.call_args.args[0],
            "https://api.brawlstars.com/v1/players/%23RLJP2JCR",
        )

    def test_missing_player_is_invalid(self):
        self.respond(404, {"reason": "notFound"})
        self.assertEqual(self.lookup("RLJP2JCR"), (None, "RLJP2JCR", False))

    def test_api_errors_are_not_invalid_ids_and_are_logged(self):
        for status, reason in (
            (400, "badRequest"),
            (401, "accessDenied"),
            (403, "accessDenied.invalidIp"),
            (403, "accessDenied"),
            (429, "tooManyRequests"),
            (500, "unknownException"),
            (503, "inMaintenance"),
        ):
            with self.subTest(status=status, reason=reason):
                self.logger.reset_mock()
                self.respond(status, {"reason": reason})
                self.assertEqual(self.lookup("RLJP2JCR"), (None, "RLJP2JCR", True))
                self.logger.warning.assert_called()
                logs = str(self.logger.warning.call_args_list)
                self.assertIn(str(status), logs)
                self.assertIn(reason, logs)
                self.assertNotIn("test-secret", logs)

    def test_non_json_error_is_logged(self):
        self.respond(502, None)
        self.requests.get.return_value.json.side_effect = ValueError("not JSON")
        self.assertEqual(self.lookup("RLJP2JCR"), (None, "RLJP2JCR", True))
        self.logger.warning.assert_called()

    def test_network_failure_is_logged(self):
        self.requests.get.side_effect = RequestException("timeout")
        self.assertEqual(self.lookup("RLJP2JCR"), (None, "RLJP2JCR", True))
        self.logger.warning.assert_called()

    def test_malformed_success_is_not_a_player(self):
        for payload in ([], {}, {"reason": "unexpected"}, None):
            with self.subTest(payload=payload):
                self.respond(200, payload)
                self.assertEqual(self.lookup("RLJP2JCR"), (None, "RLJP2JCR", True))


if __name__ == "__main__":
    unittest.main()