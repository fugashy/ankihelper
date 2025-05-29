import os

from icecream import ic
import click
import torch
from diffusers import StableDiffusionPipeline
import huggingface_hub


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
            "runwayml/stable-diffusion-v1-5",  # float32 リアル 濃い
            "gsdf/Counterfeit-V2.5",  # float32 アニメ風 淡い
            "Lykon/dreamshaper-7",  # float32 3Dアニメ風 濃い
            "Meina/MeinaMix_V11",  # float32 アニメ風
            ]),
        default="Meina/MeinaMix_V11")
@click.option("--image-width", type=int, default=720)
@click.option("--image-height", type=int, default=480)
@click.option("--output-dir-path", "-o", type=str, default="/tmp")
@click.option("--huggingface-token", type=str, default=os.environ.get("HUGGINGFACE_TOKEN"))
@click.option("--safety", is_flag=True, default=False)
@click.pass_context
def from_text(
        ctx,
        text,
        model,
        image_width,
        image_height,
        output_dir_path,
        huggingface_token,
        safety):
    if huggingface_token is not None:
        ic("use hugging face token to use models")
        huggingface_hub.login(huggingface_token)

    if safety:
        create_pipe = lambda model, dtype: StableDiffusionPipeline.from_pretrained(
                model, torch_dtype=dtype)
    else:
        create_pipe = lambda model, dtype: StableDiffusionPipeline.from_pretrained(
                model, torch_dtype=dtype, safety_checker=None)

    try:
        pipe = create_pipe(model, torch.float32)
        ic("use float32")
    except:
        pipe = create_pipe(model, torch.float16)
        ic("use float16")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    ic(device)
    pipe = pipe.to(device)

    images = pipe(
            prompt=text,
            negative_prompt="ext, letters, words, watermark, negative",
            height=image_height,
            width=image_width).images

    for i, img in enumerate(images):
        imgpath = os.path.join(output_dir_path, f"image_{i:02d}.jpg")
        img.save(imgpath, format="JPEG")

