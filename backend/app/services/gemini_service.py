import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

from app.core.config import get_settings

settings = get_settings()


def _normalize_model_name(model_name: str) -> str:
    cleaned = (model_name or "").strip()
    if cleaned.startswith("models/"):
        cleaned = cleaned[len("models/") :]
    return cleaned


def _list_generate_models() -> list[str]:
    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.gemini_api_key}"
    req = Request(url=list_url, method="GET")
    with urlopen(req, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    models = []
    for model in body.get("models", []):
        methods = model.get("supportedGenerationMethods") or []
        if "generateContent" in methods:
            name = model.get("name", "")
            if name.startswith("models/"):
                name = name[len("models/") :]
            if name:
                models.append(name)
    return models


def _post_generate_content(model_name: str, payload: dict) -> dict:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_normalize_model_name(model_name)}:generateContent?key={settings.gemini_api_key}"
    )
    req = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_api_error_message(exc: HTTPError) -> str:
    try:
        error_body = exc.read().decode("utf-8")
        parsed = json.loads(error_body)
        api_message = parsed.get("error", {}).get("message")
        if api_message:
            return str(api_message)
    except Exception:
        pass
    return str(exc.reason)


def _is_transient_generation_error(status_code: int, message: str) -> bool:
    lowered = (message or "").lower()
    return (
        status_code in {429, 500, 503}
        or "high demand" in lowered
        or "try again later" in lowered
        or "resource exhausted" in lowered
        or "temporarily unavailable" in lowered
    )


def _generation_model_order() -> list[str]:
    requested = _normalize_model_name(settings.gemini_model)
    preferred_defaults = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    available_models: list[str] = []
    try:
        available_models = _list_generate_models()
    except Exception:
        available_models = []

    ordered: list[str] = []
    if requested:
        ordered.append(requested)

    if available_models:
        for model in preferred_defaults:
            if model in available_models and model not in ordered:
                ordered.append(model)
        for model in available_models:
            if model not in ordered:
                ordered.append(model)
    else:
        for model in preferred_defaults:
            if model not in ordered:
                ordered.append(model)
    return ordered


def generate_gemini_reply(
    prompt: str,
    *,
    temperature: float = 0.3,
    max_output_tokens: int = 512,
) -> str:
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini API is not configured. Set GEMINI_API_KEY first.",
        )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }

    last_detail = "Unable to generate response right now."
    models_to_try = _generation_model_order()[:5]

    for model_name in models_to_try:
        for attempt in range(3):
            try:
                body = _post_generate_content(model_name, payload)
                candidates = body.get("candidates") or []
                if not candidates:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Gemini returned no candidate response.",
                    )

                parts = candidates[0].get("content", {}).get("parts", [])
                texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
                reply = "\n".join(text for text in texts if text).strip()
                if not reply:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Gemini returned an empty response.",
                    )
                return reply
            except HTTPError as exc:
                api_message = _extract_api_error_message(exc)
                last_detail = f"Gemini API error: {api_message}"

                is_model_error = exc.code == 404 and "generatecontent" in api_message.lower()
                if is_model_error:
                    break

                if _is_transient_generation_error(exc.code, api_message):
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    break

                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=last_detail) from exc
            except URLError as exc:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Unable to reach Gemini API.",
                ) from exc

    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=last_detail)
