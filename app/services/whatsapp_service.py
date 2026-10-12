import httpx
from app.config import Settings, get_settings
from app.services.natlas_service import IntegrationNotConfigured, UpstreamFailure

class WhatsAppService:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.client = client

    def _configured(self):
        s = self.settings
        if not s.whatsapp_enabled or not all([s.whatsapp_access_token, s.whatsapp_phone_number_id, s.meta_graph_api_version]):
            raise IntegrationNotConfigured("WhatsApp integration is not configured")

    def _url(self, suffix: str) -> str:
        self._configured()
        return f"https://graph.facebook.com/{self.settings.meta_graph_api_version}/{suffix}"

    async def _request(self, method: str, url: str, **kwargs):
        try:
            if self.client:
                r = await self.client.request(method, url, headers={"Authorization": f"Bearer {self.settings.whatsapp_access_token}"}, timeout=20, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.request(method, url, headers={"Authorization": f"Bearer {self.settings.whatsapp_access_token}"}, **kwargs)
            r.raise_for_status()
            return r
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamFailure(f"WhatsApp request failed: {type(exc).__name__}") from None

    async def send_text_message(self, recipient: str, text: str, reply_to_message_id: str | None = None) -> str:
        if not text or len(text) > 4096:
            raise ValueError("WhatsApp text must contain 1 to 4096 characters")
        body = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": recipient,
                "type": "text", "text": {"preview_url": False, "body": text}}
        if reply_to_message_id:
            body["context"] = {"message_id": reply_to_message_id}
        r = await self._request("POST", self._url(f"{self.settings.whatsapp_phone_number_id}/messages"), json=body)
        try: return r.json()["messages"][0]["id"]
        except (ValueError, KeyError, IndexError, TypeError): raise UpstreamFailure("Unexpected WhatsApp send response") from None

    async def download_media(self, media_id: str, max_bytes: int) -> tuple[bytes, str, str]:
        meta = await self._request("GET", self._url(media_id))
        try: media_url, mime = meta.json()["url"], meta.json().get("mime_type", "")
        except (ValueError, KeyError, TypeError): raise UpstreamFailure("Unexpected media metadata") from None
        extensions={"audio/ogg":"ogg","audio/opus":"opus","audio/mpeg":"mp3","audio/mp3":"mp3","audio/mp4":"m4a","audio/x-m4a":"m4a","audio/wav":"wav","audio/x-wav":"wav","audio/flac":"flac"}
        suffix=extensions.get(mime.split(';',1)[0].lower())
        if not suffix: raise ValueError("Unsupported media type")
        r = await self._request("GET", media_url)
        if r.headers.get("content-length") and int(r.headers["content-length"])>max_bytes: raise ValueError("Audio exceeds configured size limit")
        if len(r.content) > max_bytes: raise ValueError("Audio exceeds configured size limit")
        return r.content, mime, media_id + "." + suffix
