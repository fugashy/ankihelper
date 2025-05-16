import os

import click
import torch
from diffusers import StableDiffusionPipeline


@click.group()
@click.pass_context
def image(ctx):
    pass


@image.command()
@click.argument("text", type=str)
@click.option(
        "--model",
        type=click.Choice([
            "SG161222/Realistic_Vision_V5.1_noVAE",
            "runwayml/stable-diffusion-v1-5",
            ]),
        default="SG161222/Realistic_Vision_V5.1_noVAE")
@click.option(
        "--prefix",
        "-p",
        type=str,
        default='The atmosphere associated with the English sentence')
@click.option("--image-width", type=int, default=720)
@click.option("--image-height", type=int, default=480)
@click.option("--output-dir-path", "-o", type=str, default="/tmp")
@click.pass_context
def from_text(
        ctx,
        text,
        model,
        prefix,
        image_width,
        image_height,
        output_dir_path):
    pipe = StableDiffusionPipeline.from_pretrained(model, torch_dtype=torch.float16)
    pipe.to(torch.device("mps"))

    images = pipe(
            prompt=f'{prefix}: "{text}"',
            negative_prompt="ext, letters, words, watermark, negative",
            height=image_height,
            width=image_width).images

    for i, img in enumerate(images):
        imgpath = os.path.join(output_dir_path, f"image_{i:02d}.jpg")
        img.save(imgpath, format="JPEG")

