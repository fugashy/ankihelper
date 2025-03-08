import click

from .deck import deck
from .audio import audio


@click.group()
def ankihelper():
    pass



def main():
    commands = [
            deck,
            audio,
            ]
    [
        ankihelper.add_command(c)
        for c in commands
        ]

    ankihelper()
