import os

import genanki
import pandas as pd


def get_deck_helper_types():
    return ["listening", "reading_question"]


def create_deck_helper(type_, input_filepaths, model_id):
    if type_ not in get_deck_helper_types():
        return None

    if type_ == "listening":
        return ListeningDeckHelper(input_filepaths, model_id)
    elif type_ == "reading_question":
        return None


class DeckHelper():
    def __init__(self, input_filepaths, model_id):
        self._dfs = [
                pd.read_csv(
                    input_filepath, header=0, usecols=self._get_cols())
                for input_filepath in input_filepaths]
        self.model_id = model_id
        self._gen = self._extract_row()

    def _extract_row(self):
        for df in self._dfs:
            for row in df.itertuples():
                yield row

    def _get_cols(self):
        raise NotImplementedError

    def _generate_model(self):
        raise NotImplementedError

    def generate_note(self):

        try:
            row = next(self._gen)
            print(row)
        except StopIteration:
            return None, None

        return self._generate_note(row)

    def _generate_note(self, row):
        raise NotImplementedError



class ListeningDeckHelper(DeckHelper):
    def __init__(self, input_filepaths, model_id):
        super().__init__(input_filepaths, model_id)

    def _get_cols(self):
        return ["en", "jp", "en_audio"]

    def _generate_model(self):
        template = {
                "name": "Listening Card",
                "qfmt": '{{Audio}}<br>What did they say?',
                "afmt": '{{FrontSide}}<hr>{{EN}}<hr>{{JP}}<hr>{{MEMO}}'
            }

        return genanki.Model(
                self.model_id,
                template["name"],
                fields=[
                    {"name": "JP"},
                    {"name": "EN"},
                    {"name": "Audio"},
                    {"name": "MEMO"},
                    ],
                templates=[template])

    def _generate_note(self, row):
        audio_filename = os.path.basename(row.en_audio)
        return row.en_audio, genanki.Note(
            model=self._generate_model(),
            fields=[
                row.jp,
                row.en,
                audio_filename.replace(audio_filename, f"[sound:{audio_filename}]"),
                ""])
