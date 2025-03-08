import click

from .audio import audio
from .table import table


@click.group()
def ankihelper():
    pass



def main():
    commands = [
            audio,
            table,
            ]
    [
        ankihelper.add_command(c)
        for c in commands
        ]

    ankihelper()
