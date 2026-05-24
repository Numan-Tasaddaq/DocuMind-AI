from pydantic import BaseModel, Field


class GeminiChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=12000)
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=512, ge=1, le=4096)


class GeminiChatResponse(BaseModel):
    model: str
    reply: str
