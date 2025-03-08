import os
import time
import random
import shutil
import json
from glob import glob

import click
import pandas as pd
from googletrans import Translator
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sentence_transformers import SentenceTransformer
from scipy.cluster.hierarchy import linkage, fcluster
from googletrans import Translator

from .utils import (
        extract_english_from_vtt,
        )


@click.group()
def table():
    pass


@table.command()
@click.argument("input_audio_dir", type=str)
@click.argument("input_vtt_dir", type=str)
@click.option("--output_table_filepath", type=str, default="/tmp/vtt.csv")
def from_audio_vtt(input_audio_dir, input_vtt_dir, output_table_filepath):
    audio_filepaths = sorted(glob(os.path.join(input_audio_dir, "*.mp3")))
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
    df.to_csv(output_table_filepath)


@table.command()
@click.argument("input_table_filepath", type=str)
@click.option("--output_table_filepath", type=str, default="/tmp/table-with-trans.csv")
def add_trans(input_table_filepath, output_table_filepath):
    df = pd.read_csv(input_table_filepath, header=0)

    translator = Translator()

    def translate_text(text, retries=3):
        print(f"try to translate: {text}")
        for attempt in range(retries):
            try:
                translation = translator.translate(text, src="en", dest="ja").text
                time.sleep(random.uniform(1, 3))  # 1〜3秒のランダムな遅延
                return translation
            except Exception as e:
                print(f"⚠️ Too many requests: {e}")
                time.sleep(5)  # 5秒待機してリトライ
        return "Error"

    df["jp"] = df["en"].apply(lambda x: translate_text(x))
    df.to_csv(output_table_filepath, index=False)


@table.command()
@click.argument("input_table_filepath", type=str)
@click.option("--output_audio_dirpath", type=str, default="/tmp/audio")
@click.option("--output_table_filepath", type=str, default="/tmp/table-with-audio.csv")
def add_audio(input_table_filepath, output_audio_dirpath, output_table_filepath):
    df = pd.read_csv(input_table_filepath)
    english_texts = df["en"]

    shutil.rmtree(output_audio_dirpath)
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


