import ast
from pathlib import Path


def main():
    p = Path(__file__).resolve().parent.parent / "main.py"
    src = p.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(p))
    except SyntaxError as e:
        print("SYNTAX ERROR:", e)
        raise SystemExit(1)
    print("OK")


if __name__ == "__main__":
    main()

