import os
from pathlib import Path
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    python = root / ".venv" / "bin" / "python"
    if Path(sys.prefix).resolve() != (root / ".venv").resolve():
        os.execv(
            str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]]
        )
    os.chdir(root)
    sys.argv.insert(1, "--local")
    import asyncio
    from travel_agent.__main__ import main

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(
            "\nДиалог остановлен. Сохранённые шаги останутся доступны при следующем запуске."
        )
