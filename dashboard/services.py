import re
import logging
import requests
from django.conf import settings
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

logger = logging.getLogger(__name__)


def inject_ref_param(text, chat_id):
    def add_ref(url_str):
        try:
            parsed = urlparse(url_str)
            if parsed.scheme not in ("http", "https"):
                return url_str
            qs = parse_qs(parsed.query)
            qs["ref"] = [chat_id]
            new_query = urlencode({k: v[0] for k, v in qs.items()}, doseq=True)
            return urlunparse(parsed._replace(query=new_query))
        except Exception:
            return url_str

    url_pattern = re.compile(
        r'(https?://[^\s<>"\']+)'
    )
    return url_pattern.sub(lambda m: add_ref(m.group(1)), text)


class TelegramService:
    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token=None):
        self.token = token or settings.TELEGRAM_BOT_TOKEN

    def _build_url(self, method):
        return self.BASE_URL.format(token=self.token, method=method)

    def send_message(self, chat_id, text, parse_mode="HTML"):
        text = inject_ref_param(text, str(chat_id))
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        try:
            resp = requests.post(self._build_url("sendMessage"), json=payload, timeout=30)
            resp.raise_for_status()
            return {"ok": True, "result": resp.json()}
        except requests.RequestException as e:
            logger.error("Telegram send_message error: %s", e)
            return {"ok": False, "error": str(e)}

    def send_photo(self, chat_id, photo, caption="", parse_mode="HTML"):
        caption = inject_ref_param(caption, str(chat_id))
        payload = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": parse_mode,
        }
        files = None
        try:
            if hasattr(photo, "read"):
                filename = getattr(photo, "name", "product.jpg")
                # Ensure content type is set for Telegram to accept the image
                files = {"photo": (filename, photo, "image/jpeg")}
            else:
                payload["photo"] = photo
            resp = requests.post(
                self._build_url("sendPhoto"),
                data=payload,
                files=files,
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            # Telegram API can return 200 but with ok: false
            if not result.get("ok"):
                error_desc = result.get("description", "Unknown Telegram error")
                logger.error("Telegram API error: %s", error_desc)
                return {"ok": False, "error": error_desc}
            return {"ok": True, "result": result}
        except requests.RequestException as e:
            logger.error("Telegram send_photo error: %s", e)
            return {"ok": False, "error": str(e)}

    def send_message_with_image(self, chat_id, text, image_url=None, image_file=None):
        if image_url:
            return self.send_photo(chat_id, image_url, caption=text)
        if image_file:
            return self.send_photo(chat_id, image_file, caption=text)
        return self.send_message(chat_id, text)

    def send_bulk_messages(self, recipients, text, image_url=None, image_file=None):
        results = {"sent": 0, "failed": 0, "errors": []}
        for r in recipients:
            name = r.get("name", "")
            chat_id = r.get("chat_id", "")
            personalized = text.replace("{name}", name)
            if image_url or image_file:
                res = self.send_message_with_image(chat_id, personalized, image_url, image_file)
            else:
                res = self.send_message(chat_id, personalized)
            if res["ok"]:
                results["sent"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({"chat_id": chat_id, "error": res.get("error", "Unknown")})
        return results
