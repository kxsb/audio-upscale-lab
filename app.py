from pathlib import Path

import webview

from backend.api import AppApi


BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    api = AppApi(base_dir=BASE_DIR)
    index_file = BASE_DIR / "ui" / "index.html"

    webview.create_window(
        title="Audio Upscale Lab",
        url=index_file.resolve().as_uri(),
        js_api=api,
        width=1320,
        height=900,
        min_size=(1100, 760),
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()