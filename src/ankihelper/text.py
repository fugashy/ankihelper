import os
import shutil

import click
from icecream import ic
import pdfplumber



@click.group()
def text():
    pass

@text.command()
@click.argument("input_filepath", type=str)
@click.option("-o", "--output_dirpath", type=str, default="/tmp")
def from_pdf(input_filepath, output_dirpath):
    filename = ic(os.path.basename(input_filepath))
    ic(output_dirpath)
    os.makedirs(output_dirpath, exist_ok=True)
    with pdfplumber.open(input_filepath) as pdf:
        for i, page in enumerate(pdf.pages):
            with open(
                    os.path.join(
                        output_dirpath,
                        f"{filename}_{i:02d}.txt"),
                    "w") as f:
                f.write(page.extract_text())
