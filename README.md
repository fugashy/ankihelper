# ankihelper

Command tool to support deck creation for learning application anki.

## How to install

```bash
cd /path/to/this/package
pip install .
```

## How to use

### Create a deck from a voice data

- Pattern A

  When using a audio file that contain long talks

  ```bash
  ankihelper audio to-script /path/to/audio
  ankihelper text fix-whisper-result /tmp/script.json
  ankihelper table from-audio-vtt-pair /path/to/audio /tmp/new-script.vtt
  ankihelper table add-trans /tmp/table.csv
  ankihelper deck from-table /tmp/table-with-trans.csv
  ```

- Pattern B

  When using unit-by-unit audio data such as some learning materials for english.

  ```bash
  ankihelper audio to-script /path/to/audio_dir/*.mp3
  ankihelper table from-audio-vtt-pairs /path/to/audio_dir /tmp/script
  ankihelper table add-trans /tmp/table.csv
  ankihelper deck from-table /tmp/table-with-trans --output_filepath /tmp/YOUR.apkg
  ```

### Create a deck from a table

- Pattern A

  From a csv file that have columns "en" and "jp"

  ```bash
  # create and add an audio columm
  ankihelper table add-audio /path/to/csvfile

  # create deck (output path: /tmp/table.apkg)
  ankihelper deck from-table /tmp/table-with-audio.csv
  ```

- Pattern B

  From a csv file that have a column "en"

  ```bash
  ankihelper table add-trans /path/to/csvfile
  ankihelper table add-audio /path/to/table-with-trans
  ankihelper deck from-table /tmp/table-with-audio.csv
  ```

### Create a deck from your English diary

```bash
T.B.D
```
