from __future__ import annotations

import os

import uvicorn

from qnu_copilot.app import create_app


def main() -> None:
    data_root = os.environ.get("QNU_COPILOT_DATA_ROOT")
    app = create_app(data_root=data_root)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
