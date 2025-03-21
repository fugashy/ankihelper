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

  When using unit-by-unit audio data such as that included in learning materials.

  ```bash
  # clip all audio data (the output path is /tmp/clip by default)
  for f in /path/to/dir/contain/audio/data/*.mp3; do ankihelper audio "$f" clip-per-silence; done

  # Move audio data for learning to another directory, etc.

  # create scripts with each audio files
  for f in /tmp/cliped/*.mp3; do ankihelper audio "$f" to-script; done

  # create table from the audio clips and the scripts
  ankihelper table from-audio-vtt-pairs /tmp/cliped /tmp/script
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

### Create a deck from your English diary

```bash
T.B.D
```
