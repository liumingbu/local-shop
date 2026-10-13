import uvicorn
from pydantic import ValidationError

from .config import Settings
from .main import create_app

try:
    settings = Settings()
except ValidationError:
    raise SystemExit("Invalid configuration; check .env.example (values suppressed)") from None

uvicorn.run(
    create_app(settings), host=settings.api_host, port=settings.api_port, proxy_headers=False
)
