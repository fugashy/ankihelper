import os
import shutil
import json
from collections import defaultdict

import click
from icecream import ic
import pdfplumber
import pandas as pd
from PIL import Image
import pytesseract
from gtts import gTTS
import spacy
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm


from .utils import (
        format_timestamp,
        create_translator,
        )



@click.group()
def text():
    pass


@text.command()
@click.argument("input_text", type=str)
@click.option("--output-dirpath", type=str, default="/tmp")
@click.option("--output-filename", type=str, default=None)
@click.option("--lang", "-l", type=click.Choice(["en", "jp"]), default="en")
def to_audio(input_text, output_dirpath, output_filename, lang):
    ic(input_text)

    tts = gTTS(input_text, lang=lang)
    if output_filename is None:
        output_filename = input_text.lower().replace(" ", "-").strip("'\`\"\'.[]()!?/\\")
    output_filepath = os.path.join(
            output_dirpath,
            f"{output_filename}.mp3")
    tts.save(output_filepath)
    ic(output_filepath)


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
@click.argument("input_text", type=str)
@click.option(
        "--client-type",
        type=click.Choice(
            ["google-trans", "gcloud"]),
        default="google-trans")
@click.option("--src", type=click.Choice(["en", "ja"]), default="en")
@click.option("--dest", type=click.Choice(["en", "ja"]), default="ja")
def translate(input_text, client_type, src, dest):
    translator = create_translator(client_type)

    translated_text = translator.translate(
            text=input_text,
            src=src,
            dest=dest)

    with open("/tmp/translated.txt", "w") as f:
        f.write(translated_text)


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

@text.command()
@click.argument("input_filepath", type=str)
def fix_whisper_result(input_filepath):
    ic(input_filepath)
    ic.disable()
    with open(input_filepath, "r") as f:
        result = json.load(f)

    all_text = ic(" ".join([seg["text"].strip() for seg in result["segments"]]))

    nlp = spacy.load("en_core_web_sm")
    doc = nlp(all_text)
    sentences = ic([sent.text.strip() for sent in doc.sents])

    for s in sentences:
        print("---")
        print(s)

    new_segments = []
    current_pos = 0
    words = [w for s in result["segments"] for w in s.get("words", [])]

    for sentence in sentences:
        sentence_words = sentence.split()
        n = len(sentence_words)

        # 該当する単語を元のwordリストから探す
        for i in range(current_pos, len(words) - n + 1):
            if [w["word"].strip() for w in words[i:i+n]] == sentence_words:
                start_time = words[i]["start"]
                end_time = words[i+n-1]["end"]
                new_segments.append({
                    "start": start_time,
                    "end": end_time,
                    "text": sentence
                })
                current_pos = i + n
                break

    with open("/tmp/new-script.vtt", "w") as f:
        f.write("WEBVTT\n\n")
        for seg in new_segments:
            # print(f"[{format_timestamp(seg['start'])} - {format_timestamp(seg['end'])}] {seg['text']}")
            f.write(f"{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}\n")
            f.write(f"{seg['text']}\n\n")


@text.command()
@click.argument("input_filepath", type=str)
@click.option("--output_filepath", type=str, default="/tmp/script-inspected.csv")
def inspect_whisper_result(input_filepath, output_filepath):
    ic(input_filepath)

    with open(input_filepath, "r") as f:
        result = json.load(f)

    spec_by = defaultdict(list)
    for seg in result["segments"]:
        for word in seg["words"]:
            w = word["word"].strip(" -.,!?\"").lower()
            dt = word["end"] - word["start"]
            spec_by[w].append(dt)

    ic(spec_by)
    out = list()
    for word, dts in spec_by.items():
        out.append({
            "word": word,
            "num": len(dts),
            "dt_mean": np.mean(dts),
            "dt_std": np.std(dts),
            "dt_med": np.median(dts),
            "dt_max": np.max(dts),
            "dt_min": np.min(dts),
            })

    df = pd.DataFrame.from_dict(out)
    df.to_csv(output_filepath, index=False)
    ic(output_filepath)


@text.command()
@click.argument("input_filepath", type=str)
@click.option("--num-per-group", type=int, default=20)
@click.option("--output_dir", type=str, default="/tmp")
def show_word_frequency(input_filepath, num_per_group, output_dir):
    ic(input_filepath)
    df = pd.read_csv(input_filepath, header=0)
    df = df.sort_values("num", ascending=True).reset_index(drop=True)

    print(f'word num: {len(df["word"])}')

    n = ic(len(df))
    ic(num_per_group)
    group_num = ic(int(n / float(num_per_group)))
    ns = [0] + [num_per_group * (i+1) for i in range(group_num)]

    remain_num = ic(int(n % float(num_per_group)))
    if remain_num < num_per_group:
        ns[-1] += remain_num
    else:
        ns += [remain_num]
    ic(ns[0], ns[1], ns[-1])


    top_n = int(0.3 * n)
    mid_n = int(0.4 * n)

    dfs = [
            df.iloc[i:j]
            for i, j in zip(ns, ns[1:])]

    for i in tqdm(range(len(dfs))):
        df = dfs[i]
        plt.figure(figsize=(10, 6))
        plt.barh(
                df["word"],
                df["num"])
        plt.title(f"Word frequency")
        plt.xlabel("Word")
        plt.ylabel("Frequency[-]")
        plt.savefig(f"{output_dir}/freq-{i:04d}.png")
        plt.close()
