"""Baixa o modelo oficial em arquivo temporario; so publica ao concluir."""
import argparse
import os
from pathlib import Path
import shutil
import tempfile
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=("tiny", "base", "small"), default="base", nargs="?")
    args = parser.parse_args()
    directory = Path("/models")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"ggml-{args.model}.bin"
    if target.is_file() and target.stat().st_size > 0:
        print(f"Modelo ja disponivel: {target}")
        return
    url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{target.name}"
    print(f"Baixando modelo {args.model} de {url}", flush=True)
    temporary = None
    try:
        with urlopen(url, timeout=120) as response, tempfile.NamedTemporaryFile(
            dir=directory, suffix=".part", delete=False
        ) as output:
            temporary = Path(output.name)
            shutil.copyfileobj(response, output)
            expected = response.headers.get("Content-Length")
        size = temporary.stat().st_size
        if size == 0 or (expected is not None and size != int(expected)):
            raise RuntimeError("Download incompleto; execute novamente.")
        os.replace(temporary, target)
        print(f"Modelo pronto: {target} ({size / 1024**2:.1f} MiB)")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
