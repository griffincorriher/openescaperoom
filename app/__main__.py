import uvicorn

from app.config import load_config
from app.main import create_app


def main() -> None:
    config = load_config()
    uvicorn.run(
        create_app(config),
        host="0.0.0.0",
        port=config.server.port,
        reload=False,
        ws_max_size=4096,
    )


if __name__ == "__main__":
    main()
