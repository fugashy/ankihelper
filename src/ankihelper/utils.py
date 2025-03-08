from datetime import datetime, timedelta
import re

def convert_vtt_time(vtt_time, offset=0):
    """VTTの時間フォーマット (hh:mm:ss.sss) を ffmpeg 用 (hh:mm:ss) に変換し、offset(秒)を加える"""
    dt = datetime.strptime(vtt_time.replace(',', '.'), "%H:%M:%S.%f")
    dt += timedelta(seconds=offset)
    return dt.strftime("%H:%M:%S.%f")


def parse_vtt(vtt_filepath):
    print("🔍 VTT字幕を解析中...")
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
