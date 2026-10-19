from pathlib import Path
import ast
import html
import re
import shutil
import sys


def main():
    folder = Path(__file__).resolve().parent
    target = folder / "local_date_app.py"

    if not target.is_file():
        print("STOPPED: local_date_app.py was not found.")
        return 1

    original = target.read_text(encoding="utf-8-sig")
    cleaned = original

    # Remove line-break markup introduced during copying.
    cleaned = re.sub(
        r"<br\b[^>]*>",
        "\n",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove rich-text emphasis wrappers, preserving their contents.
    cleaned = re.sub(
        r"</?strong\b[^>]*>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Restore encoded Python/JavaScript operators and HTML strings.
    cleaned = html.unescape(cleaned)

    # Align this method with the other Handler class methods.
    cleaned = re.sub(
        r"^[ \t]+def do_POST\(self\):[ \t]*$",
        "    def do_POST(self):",
        cleaned,
        flags=re.MULTILINE,
    )

    # Repair known bracket artifacts from earlier responses.
    cleaned = cleaned.replace(
        "values[0\\]",
        "values[0]",
    )
    cleaned = cleaned.replace(
        'prior["schemaHash"\\]',
        'prior["schemaHash"]',
    )
    cleaned = re.sub(
        r"^([ \t]*)\\\]:[ \t]*$",
        r"\1]:",
        cleaned,
        flags=re.MULTILINE,
    )

    # Reject remaining known copy artifacts.
    if re.search(
        r"<br\b|</?strong\b|&(?:lt|gt|amp|quot);",
        cleaned,
        flags=re.IGNORECASE,
    ):
        print("STOPPED: formatting artifacts remain.")
        print("The original file was not changed.")
        return 1

    # Parse only. Do not import or execute the application.
    try:
        ast.parse(cleaned, filename=str(target))
    except SyntaxError as error:
        print("STOPPED: Python syntax still needs correction.")
        print("Line:", error.lineno)
        print("Problem:", error.msg)
        if error.text:
            print("Code:", error.text.rstrip())
        print("The original file was not changed.")
        return 1

    if cleaned == original:
        print("No repairs needed. Python syntax check passed.")
        return 0

    backup = target.with_name(
        "local_date_app.py.before_format_repair"
    )

    if backup.exists():
        print("STOPPED: a repair backup already exists:")
        print(backup)
        print("The original file was not changed.")
        return 1

    shutil.copy2(target, backup)

    temporary = target.with_name(
        "local_date_app.py.repair_pending"
    )
    temporary.write_text(cleaned, encoding="utf-8")
    temporary.replace(target)

    print("Formatting repaired. Python syntax check passed.")
    print("Backup:", backup.name)
    print()
    print("This does not validate embedded JavaScript or")
    print("prove that dashboard integration works.")
    print("Next: run START_LOCAL_DATE_APP.cmd.")
    return 0


if __name__ == "__main__":
    sys.exit(main())