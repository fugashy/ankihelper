import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from icecream import ic
import click
import pandas as pd
import genanki
import subprocess
from tqdm import tqdm
import numpy as np

from .utils import (
        convert_vtt_time,
        parse_vtt,
        )

@click.group()
def deck():
    pass


@deck.command()
@click.argument("input_filepaths", type=str, nargs=-1)
@click.option("--output_filepath", type=str, default="/tmp/table.apkg")
@click.option("--jp_major", is_flag=True, default=False)
def from_table(input_filepaths, output_filepath, jp_major):
    ic(input_filepaths)
    name = os.path.basename(output_filepath)
    dfs = [
            pd.read_csv(
                input_filepath, header=0, usecols=["en", "jp", "en_audio"])
            for input_filepath in input_filepaths]

    if jp_major:
        template = {
                "name": "Listening Card",
                "qfmt": '{{JP}}',
                "afmt": '{{FrontSide}}<hr>{{Audio}}<br>{{EN}}<br>{{MEMO}}'
            }
    else:
        template = {
                "name": "Listening Card",
                "qfmt": '{{Audio}}<br>What did they said?',
                "afmt": '{{FrontSide}}<hr>{{EN}}<br>{{JP}}<br>{{MEMO}}'
            }

    model = genanki.Model(
        28282828,
        f"{name} Model",
        fields=[
            {"name": "JP"},
            {"name": "EN"},
            {"name": "Audio"},
            {"name": "MEMO"},
            ],
        templates=[template]
    )

    deck = genanki.Deck(28282828, name)
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
                    audio_filename.replace(audio_filename, f"[sound:{audio_filename}]"),
                    ""]
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

    matches = parse_vtt(vtt_filepath)

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
        np.random.randint(0, int(1e10)),
        f"{audio_name} Listening Model",
        fields=[
            {"name": "Audio"},
            {"name": "Text"},
            ],
        templates=[
            {
                "name": f"{audio_name} Listening Card",
                "qfmt": '{{Audio}}<br>'
                        'What did they say?',
                "afmt": '{{FrontSide}}<hr>{{Text}}'
            }
        ]
    )

    deck = genanki.Deck(np.random.randint(0, int(1e10)), audio_name)
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

    matches = parse_vtt(SUBTITLE_FILE)

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


