import os
import shutil
import json

import click
from icecream import ic
import pdfplumber
import pandas as pd
from PIL import Image
import pytesseract


from .utils import format_timestamp



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


@text.command()
@click.argument("input_filepaths", type=str, nargs=-1)
@click.option("-l", "--lang", type=click.Choice(["eng", "jpn"]), default="eng")
def from_image(input_filepaths, lang):
    ic(input_filepaths)
    images = [Image.open(f) for f in input_filepaths]
    ic("extract text...")
    texts = [pytesseract.image_to_string(image, lang=lang) for image in images]
    ic(texts)
    with open(f"/tmp/text-from-image-{lang}.txt", "w") as f:
        [f.write(text) for text in texts]

@text.command()
@click.argument("input_filepath", type=str)
def whisper_result_to_vtt(input_filepath):
    with open(input_filepath, "r") as f:
        result = json.load(f)
    ic.disable()
    ic(result)

    ic.enable()
    df = pd.DataFrame()
    lines = list()
    sts = list()
    ets = list()
    for seg in result["segments"]:
        line = "".join([word["word"] for word in seg["words"]])
        try:
            st = seg["words"][0]["start"]
            et = seg["words"][-1]["end"]
            if line[-1] not in ".!?":
                line += "."
        except IndexError:
            continue
        lines.append(line[1:])
        sts.append(st)
        ets.append(et)
    df["en"] = lines
    df["st"] = sts
    df["et"] = ets

    df.to_csv("/tmp/table-with-stamp.csv", index=False)

    with open("/tmp/script.vtt", "w") as f:
        f.write("WEBVTT\n\n")
        for row in df.itertuples():
            f.write(f"{format_timestamp(row.st)} --> {format_timestamp(row.et)}\n")
            f.write(f"{row.en}\n\n")
