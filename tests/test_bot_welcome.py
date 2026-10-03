import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from main import Game, WELCOME_BANNER, WELCOME_CAPTION


class BotWelcomeTests(unittest.TestCase):
    def test_private_admin_command_grants_access_without_admin_ids(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                "MINI_APP_URL": "https://example.com/app/", "ADMIN_ACCESS_CODE": "ClezzyKryt"}):
            game = Game(database=Path(temp) / "game.sqlite3", demo=False, admin_ids=set())
            game.bot_token = "test-token"
            stop = threading.Event()
            messages = []

            def fake_telegram_api(token, method, payload, timeout=35):
                if method == "getUpdates":
                    stop.set()
                    return [{"update_id": 1, "message": {"chat": {"type": "private"},
                            "from": {"id": 42, "first_name": "Игрок"}, "text": "/ClezzyKryt"}}]
                messages.append((method, payload))
                return {"message_id": 1}

            with patch("main.telegram_api", side_effect=fake_telegram_api):
                game.bot_loop(stop)
            with game.db() as db:
                self.assertTrue(game.is_admin(db, 42))
            self.assertEqual(messages[0][0], "sendMessage")
            self.assertEqual(messages[0][1]["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"],
                             "https://example.com/app/?view=admin")

    def test_start_sends_uploaded_banner_caption_and_blue_web_app_button(self):
        with tempfile.TemporaryDirectory() as temp:
            game = Game(database=Path(temp) / "game.sqlite3", demo=True)
            game.bot_token = "test-token"
            stop = threading.Event()
            requests = []

            def fake_telegram_api(token, method, payload, timeout=35):
                self.assertEqual(method, "getUpdates")
                stop.set()
                return [{"update_id": 1, "message": {"chat": {"type": "private"},
                        "from": {"id": 42, "first_name": "Игрок"}, "text": "/start"}}]

            def fake_urlopen(request, timeout=35):
                requests.append(request)
                return io.BytesIO(json.dumps({"ok": True, "result": {"message_id": 1}}).encode())

            with patch.dict(os.environ, {"MINI_APP_URL": "https://example.com/app/"}), \
                 patch("main.telegram_api", side_effect=fake_telegram_api), \
                 patch("main.urlopen", side_effect=fake_urlopen):
                game.bot_loop(stop)

        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertTrue(request.full_url.endswith("/sendPhoto"))
        self.assertIn("multipart/form-data", request.get_header("Content-type"))
        body = request.data
        self.assertIn(WELCOME_BANNER.read_bytes(), body)
        self.assertIn(WELCOME_CAPTION.encode(), body)
        self.assertIn(b'name="parse_mode"\r\n\r\nHTML\r\n', body)
        self.assertIn('"text": "🚀Играть"'.encode(), body)
        self.assertIn(b'"style": "primary"', body)
        self.assertIn(b'"url": "https://example.com/app/"', body)


if __name__ == "__main__":
    unittest.main()
