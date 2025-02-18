import click
import os
import re
import subprocess
import genanki
from yt_dlp import YoutubeDL
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

def convert_vtt_time(vtt_time, offset=0):
    """VTTの時間フォーマット (hh:mm:ss.sss) を ffmpeg 用 (hh:mm:ss) に変換し、offset(秒)を加える"""
    dt = datetime.strptime(vtt_time.replace(',', '.'), "%H:%M:%S.%f")
    dt += timedelta(seconds=offset)
    return dt.strftime("%H:%M:%S")



@click.command()
@click.argument("url", type=str)
@click.option("-aos", "--audio-offset-sec_start", type=float, default=0.)
@click.option("-aoe", "--audio-offset-sec_end", type=float, default=0.)
@click.option("-ios", "--image-offset-sec-start", type=float, default=0.)
def main(
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

    print("🔍 VTT字幕を解析中...")
    with open(SUBTITLE_FILE, "r", encoding="utf-8") as f:
        vtt_content = f.read()

    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*\n([\s\S]*?)(?=\n\d{2}:\d{2}:\d{2}|\Z)",
        re.MULTILINE
    )
    matches = pattern.findall(vtt_content)

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
        for future in as_completed(futures):
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


if __name__ == "__main__":
    exit(main())
