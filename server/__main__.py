import uvicorn

from server import APP_HOST, APP_PORT


def main() -> None:
    uvicorn.run("server.main:app", host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    main()
