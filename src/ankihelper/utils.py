from datetime import datetime, timedelta
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from icecream import ic
from tqdm import tqdm
from googletrans import Translator
from google.cloud import translate_v2 as GCloudTranslator


def convert_vtt_time(vtt_time, offset=0):
    """VTTの時間フォーマット (hh:mm:ss.sss) を ffmpeg 用 (hh:mm:ss) に変換し、offset(秒)を加える"""
    dt = datetime.strptime(vtt_time.replace(',', '.'), "%H:%M:%S.%f")
    dt += timedelta(seconds=offset)
    return dt.strftime("%H:%M:%S.%f")


def parse_vtt(vtt_filepath):
    ic("reading vtt", vtt_filepath)
    with open(vtt_filepath, "r", encoding="utf-8") as f:
        vtt_content = f.read()

    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[.,]\d{3})\s*\n([\s\S]*?)(?=\n\d{2}:\d{2}:\d{2}|\Z)",
        re.MULTILINE
    )

    return pattern.findall(vtt_content)


def extract_english_from_vtt(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    extracted_text = []
    for line in lines:
        line = line.strip()

        if "WEBVTT" in line:
            continue

        if re.match(r'\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}', line):
            continue

        line = re.sub(r'<[^>]+>', '', line)
        if re.search(r'[a-zA-Z]', line):
            extracted_text.append(line)

    return "\n".join(extracted_text)


def format_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:06.3f}".replace('.', ',')


def save_whisper_result_as_vtt(result, output_filepath):
    sentenses = list()
    ranges = list()
    tmp = list()
    st = None
    et = None
    for seg in result["segments"]:
        for word in seg["words"]:
            if st is None:
                st = word["start"]
            tmp.append(word["word"])

            if "Mr." in word["word"]:
                continue

            if "." in word["word"] or "?" in word["word"]:
                et = word["end"]
                sentenses.append(tmp)
                ranges.append((st, et))

                st = None
                et = None
                tmp = list()

    ic(len(sentenses))
    ic(len(ranges))

    with open(output_filepath, "w", encoding="utf-8") as vtt_file:
        vtt_file.write("WEBVTT\n\n")  # VTTのヘッダー

        for sentence, range_ in zip(sentenses, ranges):
            vtt_file.write(f"{format_timestamp(range_[0])} --> {format_timestamp(range_[1])}\n")
            vtt_file.write(f"{"".join(sentence)}\n\n")

    ic("done")


class ITranslator():
    def translate(
            self,
            text: str,
            src: str,
            dest: str) -> str:
        raise NotImplementedError


class GoogleTranslator(ITranslator):
    def __init__(self):
        self._translator = Translator()

    def translate(self, text, src, dest):
        return self._translator.translate(text, src=src, dest=dest).text


class GoogleCloudTranslator(ITranslator):
    def __init__(self):
        self._translator = GCloudTranslator.Client()

    def translate(self, text, src, dest):
        result = self._translator.translate(
                text,
                source_language=src,
                target_language=dest)
        return result["translatedText"]


def create_translator(type_: str):
    translator_by = {
            "google-trans": GoogleTranslator,
            "gcloud": GoogleCloudTranslator,
            }
    return translator_by[type_]()


def clip_by_script(
        audio_filepath,
        vtt_filepath,
        offset_start,
        offset_end,
        output_dirpath):

    matches = parse_vtt(vtt_filepath)

    def process_section(idx, start, end, text, audio_offset=0, image_offset=0):
        text = text.strip()
        output_audio = os.path.join(output_dirpath, f"audio-{idx:04d}.mp3")

        start_audio = convert_vtt_time(start, offset=offset_start)
        end_audio   = convert_vtt_time(end, offset=offset_end)

        subprocess.run([
            "ffmpeg", "-i", audio_filepath,
            "-ss", start_audio, "-to", end_audio,
            "-q:a", "0", "-map", "a", "-f", "mp3", output_audio, "-y"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return {
                "id": idx,
                "filename": os.path.basename(output_audio),
                "en_audio": output_audio,
                "en": text
                }

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = []
        for idx, (start, end, text) in enumerate(matches):
            futures.append(executor.submit(process_section, idx, start, end, text))
        for future in tqdm(as_completed(futures), total=len(futures)):
            try:
                results.append(future.result())
            except Exception as e:
                ic(e)

    subprocess.run(["reset"])
    return sorted(results, key=lambda x: x["id"])
