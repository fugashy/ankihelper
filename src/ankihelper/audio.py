import os
import shutil
from icecream import ic
from pydub import AudioSegment
from pydub.silence import detect_nonsilent
import torch
import whisper
import json

import click

from .utils import (
        save_whisper_result_as_vtt,
        )

@click.group()
def audio():
    pass


@audio.command()
@click.argument("audio_filepath", type=str)
@click.option("--output_dir", type=str, default="/tmp/cliped")
@click.option("--min_silence_len", type=int, default=500)
@click.option("--silence_thresh", type=int, default=-60)
def clip_per_silence(audio_filepath, output_dir, min_silence_len, silence_thresh):
    os.makedirs(output_dir, exist_ok=True)
    input_filename = audio_filepath.split("/")[-1].split(".")[0]
    audio = AudioSegment.from_file(ctx.obj["audio_filepath"])
    # 無音でない区間を取得（開始時間, 終了時間 のリスト）
    nonsilent_chunks = detect_nonsilent(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_thresh)

    for i, (start, end) in enumerate(nonsilent_chunks):
        chunk = audio[start:end]
        chunk.export(f"{output_dir}/{input_filename}_{i}.mp3", format="mp3")
        print(f"Saved: {input_filename}_{i}.mp3 ({start}ms - {end}ms)")


@audio.command()
@click.argument("audio_filepaths", type=str, nargs=-1)
@click.option("--output_dir", type=str, default="/tmp/script")
@click.pass_context
def to_script(ctx, audio_filepaths, output_dir):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    ic(device)
    try:
        model = whisper.load_model("small").to(device)
        ic("Use MPS")
    except NotImplementedError as e:
        ic(e)
        model = whisper.load_model("small", device="cpu")
        ic("Use CPU")
    for filepath in audio_filepaths:
        result = model.transcribe(
                filepath,
                word_timestamps=True)
        with open("/tmp/script.json", "w") as f:
            json.dump(result, f, indent=2)

        os.makedirs(output_dir, exist_ok=True)
        output_filename = f'{os.path.basename(filepath)}.vtt'
        save_whisper_result_as_vtt(result, os.path.join(output_dir, output_filename))
