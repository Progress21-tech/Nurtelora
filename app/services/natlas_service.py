import httpx
from app.config import Settings, get_settings

class IntegrationNotConfigured(RuntimeError): pass
class UpstreamFailure(RuntimeError): pass

class NAtlasService:
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None):
        self.settings = settings or get_settings()
        self.client = client

    def _base(self) -> str:
        s = self.settings
        if not s.natlas_enabled or not s.natlas_base_url or not s.natlas_api_key:
            raise IntegrationNotConfigured("N-ATLAS integration is not configured")
        return s.natlas_base_url.rstrip("/")

    def _url(self, path: str) -> str:
        base = self._base()
        return base + (path if base.endswith("/v1") else "/v1" + path)

    async def _request(self, method: str, url: str, **kwargs):
        headers = {"Authorization": f"Bearer {self.settings.natlas_api_key}"}
        try:
            if self.client:
                response = await self.client.request(method, url, headers=headers, timeout=self.settings.natlas_timeout_seconds, **kwargs)
            else:
                async with httpx.AsyncClient(timeout=self.settings.natlas_timeout_seconds) as client:
                    response = await client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            raise UpstreamFailure(f"N-ATLAS returned HTTP {exc.response.status_code}") from None
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise UpstreamFailure(type(exc).__name__) from None

    async def transcribe_voice_note(self, audio_bytes: bytes, filename: str, language: str) -> str:
        if language not in self.settings.configured_languages:
            raise ValueError("Unsupported or unconfigured language")
        if not audio_bytes:
            raise ValueError("Audio is empty")
        if len(audio_bytes) > self.settings.max_audio_bytes:
            raise ValueError("Audio exceeds configured size limit")
        suffix=filename.rsplit('.',1)[-1].lower() if '.' in filename else 'ogg'
        mime={"ogg":"audio/ogg","opus":"audio/ogg","mp3":"audio/mpeg","m4a":"audio/mp4","mp4":"audio/mp4","wav":"audio/wav","flac":"audio/flac"}.get(suffix)
        if not mime: raise ValueError("Unsupported audio format")
        response = await self._request("POST", self._url("/audio/transcriptions"),
            data={"language": language, "response_format": "json"},
            files={"file": (filename, audio_bytes, mime)})
        try:
            text = response.json().get("text", "").strip()
        except (ValueError, AttributeError):
            raise UpstreamFailure("Unexpected transcription response") from None
        if not text:
            raise UpstreamFailure("Empty transcription response")
        return text

    async def generate_grounded_answer(self, question: str, language: str, approved_context: str) -> str:
        if language not in self.settings.configured_languages or not approved_context.strip():
            raise ValueError("A configured language and approved context are required")
        system = (f"Reply in language code {language}. Use only the approved information supplied in the user message. "
                  "If it does not contain the answer, say you cannot verify it. Do not diagnose, recommend treatment or medicine, "
                  "invent appointment dates or facility details, or override safety routing. Keep the reply brief.")
        response = await self._request("POST", self._url("/chat/completions"), json={
            "model": self.settings.natlas_model, "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Approved information:\n{approved_context}\n\nQuestion:\n{question}"}],
            "temperature": 0.1, "max_tokens": 180, "stream": False, "language": language})
        try:
            answer = response.json()["choices"][0]["message"]["content"].strip()
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise UpstreamFailure("Unexpected chat response") from None
        if not answer:
            raise UpstreamFailure("Empty chat response")
        return answer
