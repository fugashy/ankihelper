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
@click.argument("audio_filepath", type=str)
@click.pass_context
def audio(ctx, audio_filepath):
    ctx.ensure_object(dict)
    ctx.obj["audio_filepath"] = audio_filepath


@audio.command()
@click.option("--output_dir", type=str, default="/tmp/cliped")
@click.option("--min_silence_len", type=int, default=500)
@click.option("--silence_thresh", type=int, default=-60)
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
        print(f"Saved: {input_filename}_{i}.mp3 ({start}ms - {end}ms)")


@audio.command()
@click.option("--output_dir", type=str, default="/tmp/script")
@click.pass_context
def to_script(ctx, output_dir):
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    ic(device)
    try:
        model = whisper.load_model("small").to(device)
        ic("Use MPS")
    except NotImplementedError as e:
        ic(e)
        model = whisper.load_model("small", device="cpu")
        ic("Use CPU")
    result = model.transcribe(
            ctx.obj["audio_filepath"],
            word_timestamps=True)
    with open("/tmp/script.json", "w") as f:
        json.dump(result, f, indent=2)

    os.makedirs(output_dir, exist_ok=True)
    output_filename = f'{os.path.basename(ctx.obj["audio_filepath"])}.vtt'
    save_whisper_result_as_vtt(result, os.path.join(output_dir, output_filename))
