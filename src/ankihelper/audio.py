import os
import shutil
from icecream import ic
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import torch
import whisper
import json
from tqdm import tqdm

import click

from .utils import (
        save_whisper_result_as_vtt,
        )

@click.group()
def audio():
    pass


def normalize_audio(
    audio: AudioSegment,
    target_dbfs: float = -18.0,
) -> AudioSegment:
    """
    音量正規化
    """

    if audio.dBFS == float("-inf"):
        return audio

    change_in_dbfs = target_dbfs - audio.dBFS
    return audio.apply_gain(change_in_dbfs)

def trim_edges(
    audio: AudioSegment,
    silence_thresh: int = -42,
    min_silence_len: int = 100,
    keep_edge_silence_ms: int = 30,
) -> AudioSegment:
    """
    文頭・文末の無音除去
    """
    nonsilent = detect_nonsilent(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_thresh,
    )

    if not nonsilent:
        return audio

    start = max(
        0,
        nonsilent[0][0] - keep_edge_silence_ms,
    )

    end = min(
        len(audio),
        nonsilent[-1][1] + keep_edge_silence_ms,
    )

    return audio[start:end]


def compress_silence(
    audio: AudioSegment,
    silence_thresh: int = -42,
    detect_silence_len: int = 150,
    long_silence_ms: int = 700,
    target_silence_ms: int = 70,
) -> AudioSegment:
    """
    長すぎる無音だけ圧縮
    """

    nonsilent_ranges = detect_nonsilent(
        audio,
        min_silence_len=detect_silence_len,
        silence_thresh=silence_thresh,
    )

    if not nonsilent_ranges:
        return audio

    output = AudioSegment.empty()
    prev_end = 0

    for start, end in nonsilent_ranges:
        silence_duration = start - prev_end
        # 長い無音だけ圧縮
        if silence_duration > long_silence_ms:
            silence = AudioSegment.silent(
                duration=target_silence_ms
            )

        else:
            # 短いpauseは保持
            silence = AudioSegment.silent(
                duration=max(0, silence_duration)
            )

        chunk = audio[start:end]
        output += silence + chunk
        prev_end = end

    return output


@audio.command()
@click.argument("audio_filepaths", type=str, nargs=-1)
@click.option("--output_dir", type=str, default="/tmp/audio")
def filter_silence(audio_filepaths, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    for audio_filepath in tqdm(audio_filepaths):
        a = AudioSegment.from_file(audio_filepath)
        a = trim_edges(a)
        a = compress_silence(a)
        a = normalize_audio(a)
        input_filename = audio_filepath.split("/")[-1].split(".")[0]
        a.export(f"{output_dir}/{input_filename}.mp3", format="mp3")


@audio.command()
@click.argument("audio_filepaths", type=str, nargs=-1)
@click.option("--output_dir", type=str, default="/tmp/cliped")
@click.option("--min_silence_len", type=int, default=500)
@click.option("--silence_thresh", type=int, default=-60)
def clip_per_silence(audio_filepaths, output_dir, min_silence_len, silence_thresh):
    os.makedirs(output_dir, exist_ok=True)
    for audio_filepath in tqdm(audio_filepaths):
        input_filename = audio_filepath.split("/")[-1].split(".")[0]
        audio = AudioSegment.from_file(audio_filepath)
        # 無音でない区間を取得（開始時間, 終了時間 のリスト）
        nonsilent_chunks = detect_nonsilent(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh)

        for i, (start, end) in enumerate(nonsilent_chunks):
            chunk = audio[start:end]
            chunk.export(f"{output_dir}/{input_filename}_{i:04d}.mp3", format="mp3")
            print(f"Saved: {input_filename}_{i:04d}.mp3 ({start}ms - {end}ms)")


@audio.command()
@click.argument("audio_filepaths", type=str, nargs=-1)
@click.option("--output_dir", type=str, default="/tmp/script")
@click.pass_context
def to_script(ctx, audio_filepaths, output_dir):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    try:
        model = whisper.load_model("small").to(device)
        ic("Use MPS")
    except NotImplementedError as e:
        ic(e)
        model = whisper.load_model("small", device="cpu")
        ic("Use CPU")
    for filepath in tqdm(audio_filepaths):
        result = model.transcribe(
                filepath,
                word_timestamps=True,
                fp16=False)
        with open("/tmp/script.json", "w") as f:
            json.dump(result, f, indent=2)

        os.makedirs(output_dir, exist_ok=True)
        output_filename = f'{os.path.basename(filepath)}.vtt'
        save_whisper_result_as_vtt(result, os.path.join(output_dir, output_filename))
