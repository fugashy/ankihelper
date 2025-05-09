import click

from .audio import audio
from .table import table
from .deck import deck
from .diary import diary
from .text import text
from .image import image


@click.group()
def ankihelper():
    pass



def main():
    commands = [
            audio,
            table,
            deck,
            diary,
            text,
            image,
            ]
    [
        ankihelper.add_command(c)
        for c in commands
        ]

    ankihelper()
