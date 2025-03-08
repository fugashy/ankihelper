import click

from .audio import audio
from .table import table
from .deck import deck


@click.group()
def ankihelper():
    pass



def main():
    commands = [
            audio,
            table,
            deck,
            ]
    [
        ankihelper.add_command(c)
        for c in commands
        ]

    ankihelper()
