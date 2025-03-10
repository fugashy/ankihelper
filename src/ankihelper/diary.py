from datetime import datetime
import os
import shutil

import click
from gtts import gTTS
from icecream import ic
import torch
from diffusers import StableDiffusionPipeline


@click.group()
def diary():
    pass


@diary.command()
@click.argument("text", type=str)
@click.option("--image-size", type=int, default=400)
def add(text, image_size):
    # 作業ディレクトリの準備
    now = date_str = datetime.now().strftime("%Y%m%d%H%M")
    dirpath = f"/tmp/diary/{now}"
    shutil.rmtree(dirpath, ignore_errors=True)
    os.makedirs(dirpath, exist_ok=True)

    ic("writing text...")
    with open(os.path.join(dirpath, "text.txt"), "w") as f:
        f.write(text)

    ic("generate audio...")
    tts = gTTS(text, lang='en')
    tts.save(os.path.join(dirpath, "audio.mp3"))

    ic("generate image...")
    pipe = StableDiffusionPipeline.from_pretrained(
            "SG161222/Realistic_Vision_V5.1_noVAE",
            torch_dtype=torch.float16)
    pipe.to(torch.device("mps"))
    images = pipe(
            f'The atmosphere associated with the English sentence "{text}"',
            height=image_size,
            width=image_size).images
    [
        img.save(os.path.join(dirpath, f"image_{i}.jpg"))
        for i, img, in enumerate(images)
    ]
    ic("done")
