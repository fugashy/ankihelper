import os
import time
import random
import shutil
import json
from glob import glob

import click
from icecream import ic
import pandas as pd
from googletrans import Translator
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sentence_transformers import SentenceTransformer
from scipy.cluster.hierarchy import linkage, fcluster
from gtts import gTTS
import torch
from diffusers import StableDiffusionPipeline

from .utils import (
        extract_english_from_vtt,
        create_translator,
        clip_by_script,
        )


@click.group()
def table():
    pass


@table.command()
@click.argument("table_filepath", type=str)
@click.option("--rows-per-file", type=int, default=300)
@click.option("--output_dirpath", type=str, default="/tmp/chunk_df")
def split(table_filepath, rows_per_file, output_dirpath):
    shutil.rmtree(output_dirpath, ignore_errors=True)
    os.makedirs(output_dirpath, exist_ok=True)

    df = pd.read_csv(table_filepath, header=0)

    for i in range(0, len(df), rows_per_file):
        chunk_df = df.iloc[i:i+rows_per_file]
        output_filepath = os.path.join(
                output_dirpath, f"chunk_df_{i // rows_per_file + 1}.csv")
        chunk_df.to_csv(output_filepath, index=False)



@table.command()
@click.argument("table_filepath", type=str)
@click.option("--column", type=str, default="en")
def drop_duplicates(table_filepath, column):
    df = pd.read_csv(table_filepath, header=0)

    df_dropped = df.drop_duplicates(
            subset=[column],
            keep="last")
    basename = os.path.basename(table_filepath)
    df_dropped.to_csv(f"/tmp/{basename}-dropped.csv", index=False)


@table.command()
@click.argument("table_filepaths", type=str, nargs=-1)
@click.option("-o", "--output_filepath", type=str, default="/tmp/merged.csv")
def merge(table_filepaths, output_filepath):
    dfs = [pd.read_csv(f, header=0) for f in table_filepaths]
    merged_df = pd.concat(dfs)
    merged_df.to_csv(output_filepath, index=False)



@table.command()
@click.argument("input_audio_dir", type=str)
@click.argument("input_vtt_dir", type=str)
@click.option("--output_table_filepath", type=str, default="/tmp/table.csv")
def from_audio_vtt_pairs(input_audio_dir, input_vtt_dir, output_table_filepath):
    audio_filepaths = sorted(glob(os.path.join(input_audio_dir, "*")))
    vtt_filepaths = sorted(glob(os.path.join(input_vtt_dir, "*.vtt")))
    if len(audio_filepaths) != len(vtt_filepaths):
        print(f"audio_filepaths num must be the same vtt_filepaths")
        return

    eng_lines_list = [
            extract_english_from_vtt(f)
            for f in vtt_filepaths]

    df = pd.DataFrame.from_dict([
        {
            "en": lines,
            "en_audio": audio
            }
        for lines, audio in zip(eng_lines_list, audio_filepaths)])
    df.to_csv(output_table_filepath, index=False)


@table.command()
@click.argument("audio_filepath", type=str)
@click.argument("vtt_filepath", type=str)
@click.option("-aos", "--audio-offset-sec_start", type=float, default=0.)
@click.option("-aoe", "--audio-offset-sec_end", type=float, default=0.5)
@click.option("--output_dir", type=str, default="/tmp/cliped")
@click.pass_context
def from_audio_vtt_pair(
        ctx,
        audio_filepath,
        vtt_filepath,
        audio_offset_sec_start,
        audio_offset_sec_end,
        output_dir):
    os.makedirs(output_dir, exist_ok=True)

    results = clip_by_script(
            audio_filepath,
            vtt_filepath,
            audio_offset_sec_start,
            audio_offset_sec_end,
            output_dir)

    df = pd.DataFrame.from_dict(results)
    df.to_csv("/tmp/table.csv", index=False)


@table.command()
@click.argument("input_table_filepath", type=str)
@click.option("--output_table_filepath", type=str, default="/tmp/table-with-image.csv")
@click.option("--output_image_dirpath", type=str, default="/tmp/images")
@click.option("--image-size", type=int, default=512)
@click.option(
        "--model",
        type=click.Choice([
            "stabilityai/stable-diffusion-xl-base-1.0",
            "SG161222/Realistic_Vision_V5.1_noVAE",
            "runwayml/stable-diffusion-v1-5",
            ]),
        default="SG161222/Realistic_Vision_V5.1_noVAE")
def add_image(
        input_table_filepath,
        output_table_filepath,
        output_image_dirpath,
        image_size,
        model):
    pipe = StableDiffusionPipeline.from_pretrained(model, torch_dtype=torch.float16)
    pipe.to(torch.device("mps"))

    shutil.rmtree(output_image_dirpath, ignore_errors=True)
    os.makedirs(output_image_dirpath, exist_ok=True)

    df = pd.read_csv(input_table_filepath, header=0)
    image_filepaths = list()
    for i, row in enumerate(df.itertuples()):
        images = pipe(
                f'The atmosphere associated with the English sentence "{row.en}"',
                height=image_size,
                width=image_size).images
        imgpaths = list()
        for j, img in enumerate(images):
            imgpath = os.path.join(output_image_dirpath, f"image_{i}_{j}.jpg")
            imgpaths.append(imgpath)
            img.save(imgpath, format="JPEG")
        image_filepaths.append(imgpaths)

    df["image"] = image_filepaths

    df.to_csv(output_table_filepath, index=False)



@table.command()
@click.argument("input_table_filepath", type=str)
@click.option("--output_table_filepath", type=str, default="/tmp/table-with-trans.csv")
@click.option(
        "--client-type",
        type=click.Choice(
            ["google-trans", "gcloud"]),
        default="google-trans")
def add_trans(input_table_filepath, output_table_filepath, client_type):
    df = pd.read_csv(input_table_filepath, header=0)

    translator = create_translator(client_type)

    def translate_text(text, retries=3):
        print(f"try to translate: {text}")
        for attempt in range(retries):
            try:
                translation = translator.translate(text=text, src="en", dest="ja")
                if client_type != "gcloud":
                    time.sleep(random.uniform(1, 3))  # 1〜3秒のランダムな遅延
                return translation
            except Exception as e:
                print(f"{e}")
                time.sleep(5)  # 5秒待機してリトライ
        return "Error"

    df["jp"] = df["en"].apply(lambda x: translate_text(x))
    df.to_csv(output_table_filepath, index=False)


@table.command()
@click.argument("input_table_filepath", type=str)
@click.option("--output_audio_dirpath", type=str, default="/tmp/audio")
@click.option("--output_table_filepath", type=str, default="/tmp/table-with-audio.csv")
def add_audio(input_table_filepath, output_audio_dirpath, output_table_filepath):
    df = pd.read_csv(input_table_filepath, quotechar='"')
    ic(df["en"])
    english_texts = df["en"]

    shutil.rmtree(output_audio_dirpath, ignore_errors=True)
    os.makedirs(output_audio_dirpath, exist_ok=True)

    audio_paths = []
    for i, text in enumerate(english_texts):
        audio_filename = f"audio_{i+1}.mp3"
        audio_path = os.path.join(output_audio_dirpath, audio_filename)

        tts = gTTS(text, lang='en')
        tts.save(audio_path)

        audio_paths.append(audio_path)

    df['en_audio'] = audio_paths
    df.to_csv(output_table_filepath, index=False)


@table.command()
@click.argument("input_filepaths", type=str, nargs=-1)
@click.option("--output_table_filepath_csv", type=str, default="/tmp/table-with-category.csv")
@click.option("--output_table_filepath_json", type=str, default="/tmp/table-with-category.json")
@click.option("--en-key", type=str, default="en")
@click.option("--max-k", type=int, default=15)
def add_categories(
        input_filepaths,
        output_table_filepath_csv,
        output_table_filepath_json,
        en_key,
        max_k):
    dfs = [pd.read_csv(input_filepath, header=0) for input_filepath in input_filepaths]
    df = pd.concat(dfs)

    model = SentenceTransformer("all-MiniLM-L6-v2")  # 軽量なSentence-BERTモデルを使用
    embeddings = model.encode(df[en_key].tolist(), convert_to_tensor=True)
    embeddings_np = embeddings.cpu().numpy()

    wss = []
    for k in range(1, max_k):
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        kmeans.fit(embeddings_np)
        wss.append(kmeans.inertia_)

    plt.plot(range(1, max_k), wss, marker="o")
    plt.xlabel("Number of Clusters")
    plt.ylabel("WSS (Within-Cluster Sum of Squares)")
    plt.title("Elbow Method for Optimal k")
    plt.show()

    optimal_k = int(input("Enter the optimal number of clusters: "))

    kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
    df["cluster"] = kmeans.fit_predict(embeddings_np)

    tree = {"name": "English Sentences", "children": []}
    clusters = {}

    for _, row in df.iterrows():
        cluster_name = f"Cluster {row['cluster']}"
        if cluster_name not in clusters:
            clusters[cluster_name] = {"name": cluster_name, "children": []}
        clusters[cluster_name]["children"].append({"name": row[en_key]})

    tree["children"] = list(clusters.values())

    with open(output_table_filepath_json, "w") as f:
        json.dump(tree, f, indent=2)

    df.to_csv(output_table_filepath_csv, index=False)


