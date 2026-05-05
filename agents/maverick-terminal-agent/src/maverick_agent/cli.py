from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
import typer

from maverick_agent.parsers.var_pdf import VarPdfParser


app = typer.Typer(no_args_is_help=True, help="Maverick Terminal Agent - Terminal provisioning automation.")


@app.callback()
def main() -> None:
    load_dotenv()


@app.command("parse-pdf")
def parse_pdf(pdf_path: Path) -> None:
    """Parse a VAR PDF and extract field values. Useful for debugging PDF fallback."""
    payload = VarPdfParser().parse_file(pdf_path)
    typer.echo(json.dumps(payload.to_dict(), indent=2, ensure_ascii=True))


if __name__ == "__main__":
    app()
