import json
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

    body: dict | None = None
    try:
        body = _post_generate_content(settings.gemini_model, payload)
    except HTTPError as exc:
        detail = f"Gemini request failed with status {exc.code}."
        try:
            error_body = exc.read().decode("utf-8")
            parsed = json.loads(error_body)
            api_message = parsed.get("error", {}).get("message")
            if api_message:
                detail = f"Gemini API error: {api_message}"

            is_model_error = exc.code == 404 and (
                "models/" in (api_message or "") and "generateContent" in (api_message or "")
            )
            if is_model_error:
                available_models = []
                try:
                    available_models = _list_generate_models()
                except Exception:
                    available_models = []

                if available_models:
                    preferred = next(
                        (
                            model
                            for model in available_models
                            if model in {"gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"}
                        ),
                        available_models[0],
                    )
                    try:
                        body = _post_generate_content(preferred, payload)
                    except HTTPError as retry_exc:
                        retry_detail = f"Gemini API error: {retry_exc.reason}"
                        try:
                            retry_parsed = json.loads(retry_exc.read().decode("utf-8"))
                            retry_msg = retry_parsed.get("error", {}).get("message")
                            if retry_msg:
                                retry_detail = f"Gemini API error: {retry_msg}"
                        except Exception:
                            pass
                        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=retry_detail) from retry_exc
                    except URLError as retry_exc:
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Unable to reach Gemini API.",
                        ) from retry_exc
                else:
                    detail = (
                        "Gemini model is unavailable for generateContent. "
                        "Update GEMINI_MODEL to a currently supported model."
                    )
        except Exception:
            pass
        if body is None:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from exc
    except URLError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to reach Gemini API.",
        ) from exc

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
