import json
import sys
from pathlib import Path

def main(path: str) -> int:
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("JSON ERROR:", e)
        return 1
    print("JSON OK; keys:", list(data.keys()))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "_conf_schema.json"))

