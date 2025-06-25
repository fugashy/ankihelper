import os

from icecream import ic
import click
from .utils import (
        ImageGenerator,
        )



@click.group()
@click.pass_context
def image(ctx):
    pass


@image.command()
@click.argument("text", type=str)
@click.option(
        "--model-id",
        type=click.Choice(list(ImageGenerator.get_diffuser_model_name_by_id().keys())),
        default="0")
@click.option("--image-width", type=int, default=720)
@click.option("--image-height", type=int, default=480)
@click.option("--output-dir-path", "-o", type=str, default="/tmp")
@click.option("--safety", is_flag=True, default=False)
@click.pass_context
def from_text(
        ctx,
        text,
        model_id,
        image_width,
        image_height,
        output_dir_path,
        safety):
    gen = ImageGenerator(
            ImageGenerator.get_diffuser_model_name_by_id()[model_id],
            safety)

    images = gen.generate(
            text, image_height, image_width)

    for i, img in enumerate(images):
        imgpath = os.path.join(output_dir_path, f"image_{i:02d}.jpg")
        img.save(imgpath, format="JPEG")


@image.command()
def show_model_name_by_id():
    ic(ImageGenerator.get_diffuser_model_name_by_id())
