import os
import shutil
import re
import subprocess
import genanki
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import click
from tqdm import tqdm
from yt_dlp import YoutubeDL
import whisper
import torch
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import pandas as pd
from gtts import gTTS
import numpy as np
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sentence_transformers import SentenceTransformer
from scipy.cluster.hierarchy import linkage, fcluster
import json
from googletrans import Translator




def convert_vtt_time(vtt_time, offset=0):
    """VTTの時間フォーマット (hh:mm:ss.sss) を ffmpeg 用 (hh:mm:ss) に変換し、offset(秒)を加える"""
    dt = datetime.strptime(vtt_time.replace(',', '.'), "%H:%M:%S.%f")
    dt += timedelta(seconds=offset)
    return dt.strftime("%H:%M:%S.%f")


def _parse_vtt(vtt_filepath):
    print("🔍 VTT字幕を解析中...")
    with open(vtt_filepath, "r", encoding="utf-8") as f:
        vtt_content = f.read()

    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*\n([\s\S]*?)(?=\n\d{2}:\d{2}:\d{2}|\Z)",
        re.MULTILINE
    )
    return pattern.findall(vtt_content)


@click.group()
def ankihelper():
    pass


@ankihelper.group()
def table():
    pass


@table.command()
@click.argument("input_table_filepath", type=str)
@click.option("--output_table_filepath", type=str, default="/tmp/table-with-trans.csv")
def add_trans(input_table_filepath, output_table_filepath):
    df = pd.read_csv(input_table_filepath, header=0)

    translator = Translator()
    df["jp"] = df["en"].apply(
            lambda x: translator.translate(x, src="en", dest="ja").text)
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


@ankihelper.group()
def deck():
    pass


@deck.command()
@click.argument("input_filepaths", type=str, nargs=-1)
@click.option("--output_filepath", type=str, default="/tmp/table.apkg")
@click.option("--en_major", is_flag=True, default=False)
def from_table(input_filepaths, output_filepath, en_major):
    name = os.path.basename(output_filepath)
    dfs = [
            pd.read_csv(
                input_filepath, header=0, usecols=["en", "jp", "en_audio"])
            for input_filepath in input_filepaths]

    if en_major:
        template = {
                "name": "Listening Card",
                "qfmt": '{{Audio}}<br>{{EN}}',
                "afmt": '{{FrontSide}}<hr>{{JP}}'
            }
    else:
        template = {
                "name": "Listening Card",
                "qfmt": '{{JP}}',
                "afmt": '{{FrontSide}}<hr>{{Audio}}<br>{{EN}}'
            }

    model = genanki.Model(
        1234567890,
        f"{name} Model",
        fields=[
            {"name": "JP"},
            {"name": "EN"},
            {"name": "Audio"},
            ],
        templates=[template]
    )

    deck = genanki.Deck(987654321, name)
    audio_filepaths = list()
    for df in dfs:
        for row in df.itertuples():
            audio_filename = os.path.basename(row.en_audio)
            audio_filepaths.append(row.en_audio)
            note = genanki.Note(
                model=model,
                fields=[
                    row.jp,
                    row.en,
                    audio_filename.replace(audio_filename, f"[sound:{audio_filename}]")]
            )
            deck.add_note(note)

    package = genanki.Package(
        deck,
        media_files=audio_filepaths,
    )
    package.write_to_file(f"{output_filepath}")


@deck.command()
@click.argument("audio_filepath", type=str)
@click.argument("vtt_filepath", type=str)
@click.option("-aos", "--audio-offset-sec_start", type=float, default=0.)
@click.option("-aoe", "--audio-offset-sec_end", type=float, default=0.)
def from_audio_and_vtt(audio_filepath, vtt_filepath, audio_offset_sec_start, audio_offset_sec_end):
    audio_name = audio_filepath.split("/")[-1].split(".")[0]
    work_dir = f"/tmp/{audio_name}"
    AUDIO_FILE = audio_filepath
    SUBTITLE_FILE = vtt_filepath
    AUDIO_CLIPS_DIR = os.path.join(work_dir, "audio_clips")
    os.makedirs(AUDIO_CLIPS_DIR, exist_ok=True)

    matches = _parse_vtt(vtt_filepath)

    def process_section(idx, start, end, text, audio_offset=0, image_offset=0):
        text = text.strip()
        output_audio = os.path.join(AUDIO_CLIPS_DIR, f"audio-{idx}.mp3")

        start_audio = convert_vtt_time(start, offset=audio_offset_sec_start)
        end_audio   = convert_vtt_time(end, offset=audio_offset_sec_end)

        subprocess.run([
            "ffmpeg", "-i", AUDIO_FILE,
            "-ss", start_audio, "-to", end_audio,
            "-q:a", "0", "-map", "a", "-f", "mp3", output_audio, "-y"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return idx, (os.path.basename(output_audio), text)

    cards = []
    print("⚙️ 音声クリップを生成中...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for idx, (start, end, text) in enumerate(matches):
            futures.append(executor.submit(process_section, idx, start, end, text))
        for future in tqdm(as_completed(futures), total=len(futures)):
            try:
                result = future.result()
                cards.append(result)
            except Exception as e:
                print("Error processing a section:", e)

    print(f"✅ {len(cards)} 個のセクションを処理しました！")

    print("📚 Ankiデッキを作成中...")
    model = genanki.Model(
        1234567890,
        "Simple Listening Model",
        fields=[
            {"name": "Audio"},
            {"name": "Text"},
            ],
        templates=[
            {
                "name": "Listening Card",
                "qfmt": '<audio controls><source src="{{Audio}}" type="audio/mpeg"></audio><br>'
                        'What did they say?',
                "afmt": '{{FrontSide}}<hr>{{Text}}'
            }
        ]
    )

    deck = genanki.Deck(987654321, audio_name)
    for _, (audio, text) in sorted(cards):
        note = genanki.Note(
            model=model,
            fields=[audio.replace(audio, f"[sound:{audio}]"), text]
        )
        deck.add_note(note)

    output_apkg = os.path.join(work_dir, f"{audio_name}.apkg")
    package = genanki.Package(
        deck,
        media_files=
            [os.path.join(AUDIO_CLIPS_DIR, f) for f in os.listdir(AUDIO_CLIPS_DIR)]
    )
    package.write_to_file(output_apkg)

    print("🎉 Ankiデッキ作成完了！")
    print(f"📦 出力ファイル: {output_apkg}")

    subprocess.run(["reset"])


@deck.command()
@click.argument("url", type=str)
@click.option("-aos", "--audio-offset-sec_start", type=float, default=0.)
@click.option("-aoe", "--audio-offset-sec_end", type=float, default=0.)
@click.option("-ios", "--image-offset-sec-start", type=float, default=0.)
def from_web_video(
        url,
        audio_offset_sec_start,
        audio_offset_sec_end,
        image_offset_sec_start):
    movie_name = url.split("/")[-1]
    work_dir = f"/tmp/{movie_name}"
    os.makedirs(work_dir, exist_ok=True)

    VIDEO_FILE = os.path.join(work_dir, "video.mp4")
    AUDIO_FILE = os.path.join(work_dir, "audio.mp3")
    SUBTITLE_FILE = os.path.join(work_dir, "subtitle.vtt")

    AUDIO_CLIPS_DIR = os.path.join(work_dir, "audio_clips")
    SCREENSHOTS_DIR = os.path.join(work_dir, "screenshots")
    os.makedirs(AUDIO_CLIPS_DIR, exist_ok=True)
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

    if os.path.exists(VIDEO_FILE) and os.path.exists(AUDIO_FILE) and os.path.exists(SUBTITLE_FILE):
        pass
    else:
        print("📥 TED動画をダウンロード中...")
        ydl_opts = {
            "outtmpl": os.path.join(work_dir, "%(title)s.%(ext)s"),
            "format": "worst",
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en"],
            "convertsubs": "vtt",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }],
            "keepvideo": True
        }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        for file in os.listdir(work_dir):
            file_path = os.path.join(work_dir, file)
            if file.endswith(".mp4") and not os.path.exists(VIDEO_FILE):
                os.rename(file_path, VIDEO_FILE)
            elif file.endswith(".mp3") and not os.path.exists(AUDIO_FILE):
                os.rename(file_path, AUDIO_FILE)
            elif file.endswith(".vtt") and not os.path.exists(SUBTITLE_FILE):
                os.rename(file_path, SUBTITLE_FILE)

    print(f"🔹 動画: {'OK' if os.path.exists(VIDEO_FILE) else '❌'}")
    print(f"🔹 音声: {'OK' if os.path.exists(AUDIO_FILE) else '❌'}")
    print(f"🔹 字幕: {'OK' if os.path.exists(SUBTITLE_FILE) else '❌'}")

    matches = _parse_vtt(SUBTITLE_FILE)

    def process_section(idx, start, end, text, audio_offset=0, image_offset=0):
        """各セクションについて音声クリップとスクリーンショットを生成する"""
        text = text.strip()
        output_audio = os.path.join(AUDIO_CLIPS_DIR, f"audio-{idx}.mp3")
        output_image = os.path.join(SCREENSHOTS_DIR, f"image-{idx}.jpg")
        start_audio = convert_vtt_time(start, offset=audio_offset_sec_start)
        end_audio   = convert_vtt_time(end, offset=audio_offset_sec_end)
        start_image = convert_vtt_time(start, offset=image_offset_sec_start)
        subprocess.run([
            "ffmpeg", "-i", AUDIO_FILE,
            "-ss", start_audio, "-to", end_audio,
            "-q:a", "0", "-map", "a", "-f", "mp3", output_audio, "-y"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([
            "ffmpeg", "-i", VIDEO_FILE,
            "-ss", start_image, "-vframes", "1",
            "-f", "image2", output_image, "-y"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return idx, (text, os.path.basename(output_audio), os.path.basename(output_image))

    cards = []
    print("⚙️ 音声クリップとスクリーンショットを生成中...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for idx, (start, end, text) in enumerate(matches):
            futures.append(executor.submit(process_section, idx, start, end, text))
        for future in tqdm(as_completed(futures), total=len(futures)):
            try:
                result = future.result()
                cards.append(result)
            except Exception as e:
                print("Error processing a section:", e)

    print(f"✅ {len(cards)} 個のセクションを処理しました！")

    print("📚 Ankiデッキを作成中...")
    model = genanki.Model(
        1234567890,
        "TED Listening Model",
        fields=[
            {"name": "Image"},
            {"name": "Audio"},
            {"name": "Text"},
            ],
        templates=[
            {
                "name": "Listening Card",
                "qfmt": '{{Image}}<br>'
                        '<audio controls><source src="{{Audio}}" type="audio/mpeg"></audio><br>'
                        'What did they say?',
                "afmt": '{{FrontSide}}<hr>{{Text}}'
            }
        ]
    )

    deck = genanki.Deck(987654321, movie_name)
    for _, (text, audio, image) in sorted(cards):
        print(image, audio)
        note = genanki.Note(
            model=model,
            fields=[image.replace(image, f'<img src="{image}">'), audio.replace(audio, f"[sound:{audio}]"), text]
        )
        deck.add_note(note)

    output_apkg = os.path.join(work_dir, f"{movie_name}.apkg")
    package = genanki.Package(
        deck,
        media_files=
            [os.path.join(AUDIO_CLIPS_DIR, f) for f in os.listdir(AUDIO_CLIPS_DIR)]
            + [os.path.join(SCREENSHOTS_DIR, f) for f in os.listdir(SCREENSHOTS_DIR)]
    )
    package.write_to_file(output_apkg)

    print("🎉 Ankiデッキ作成完了！")
    print(f"📦 出力ファイル: {output_apkg}")

    subprocess.run(["reset"])


@ankihelper.group()
@click.argument("audio_filepath", type=str)
@click.pass_context
def audio(ctx, audio_filepath):
    ctx.ensure_object(dict)
    ctx.obj["audio_filepath"] = audio_filepath


@audio.command()
@click.option("--output_dir", type=str, default="/tmp/cliped")
@click.option("--min_silence_len", type=int, default=500)
@click.option("--silence_thresh", type=int, default=-40)
@click.pass_context
def clip_per_silence(ctx, output_dir, min_silence_len, silence_thresh):
    os.makedirs(output_dir, exist_ok=True)
    input_filename = ctx.obj["audio_filepath"].split("/")[-1].split(".")[0]
    audio = AudioSegment.from_file(ctx.obj["audio_filepath"])
    # 無音でない区間を取得（開始時間, 終了時間 のリスト）
    nonsilent_chunks = detect_nonsilent(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh)

    for i, (start, end) in enumerate(nonsilent_chunks):
        chunk = audio[start:end]
        chunk.export(f"{output_dir}/{input_filename}_{i}.mp3", format="mp3")
        print(f"Saved: {input_filename}_{i}.wav ({start}ms - {end}ms)")


@audio.command()
@click.option("--output_filepath", type=str, default="/tmp/script.vtt")
@click.pass_context
def to_script(ctx, output_filepath):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    try:
        model = whisper.load_model("small", device="cpu").to(device)
    except NotImplementedError:
        model = whisper.load_model("small", device="cpu")
    result = model.transcribe(
            ctx.obj["audio_filepath"],
            word_timestamps=True)

    with open(output_filepath, "w", encoding="utf-8") as vtt_file:
        vtt_file.write("WEBVTT\n\n")  # VTTのヘッダー

        for segment in result["segments"]:
            start = segment["start"]
            end = segment["end"]
            text = segment["text"]

            # 時間を VTT フォーマット (hh:mm:ss.sss) に変換
            def format_timestamp(seconds):
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                secs = seconds % 60
                return f"{hours:02}:{minutes:02}:{secs:06.3f}".replace('.', ',')

            vtt_file.write(f"{format_timestamp(start)} --> {format_timestamp(end)}\n")
            vtt_file.write(f"{text}\n\n")

    print(f"VTTファイルが作成されました: {output_filepath}")


if __name__ == "__main__":
    exit(ankihelper())
