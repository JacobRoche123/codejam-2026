"""Aiguilleur: ask before thinking, then pick the smallest model that does the job."""


def main() -> None:
    import uvicorn

    from .server import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
