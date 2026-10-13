# Tessituragram

Tessituragram analyzes single-track Musical Instrument Digital Interface (MIDI) files.

## Description

Users can upload single-track MIDI files into Tessituragram, which outputs metrics including vocal range, 
pitch quartiles, performance time, and time spent singing in generalized vocal *passaggi*. The program outputs results to the console and to a PDF for storage and visualization. This repository includes a test suite of 150 manually-verified vocal compositions and their corresponding MIDI files. Guidance for testing with other MIDI files is in the Data section.

## Installation

  ### Using Executable Files (Easiest Method)
  
  To run the application without installing Python and the required libraries, download main.exe (Windows) or main (Mac).
  
  ### Using Git
  * This method requires these following dependencies to install:
    * [Python 3.12.10](https://www.python.org/downloads/release/python-31210/) 
    * [Git](https://git-scm.com/install/)
  
  * Install the software by running:
    ```
    git clone https://github.com/Tessituragram/Tessituragram
    ```
  * To install all required Python libraries, navigate to the root directory (Tessituragram folder), and run:
    ```
    python install -r requirements.txt
    ```

## Executing Program main.exe (Windows) / main (Mac)

  1. Open a command line (Command Prompt or Terminal).
  2. Copy the program's folder path (right click folder containing main.exe / main and copy as path), and run `cd "path/to/folder"`.
  3. If using the Mac installation, run `chmod -x main` to allow execution.
  4. To run the program, run:
     ```
     [.\main.exe OR ./main] --filepath [PATH/TO/MIDI/FILE] --clef_range ["bass" OR "treble"] --musescore_path [PATH/TO/MUSESCORE/EXECUTABLE]
     ```
  * `--filepath` is a required argument followed by the path to the processed MIDI file.
  * `--clef_range` is an optional argument followed by "bass" or "treble" to describe the clef range of the input file. Including this argument will output
  the tessituragram analysis of the MIDI file in both treble and bass clef range. If omitted, Tessituragram processes the file as is.
  * `--musescore_path` is an optional argument followed by the path to the Musescore executable on your machine (`'C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe'`, for example). The program searches for MuseScore installation by default, and this is intended to only be used if the Musescore path cannot be found by Tessituragram. The program will still run without MuseScore installation but will not provide score visualization in the output PDF.
 
  * Example:
    ```
    .\main.exe --filepath "data\test_data_arias\1-I.mid" --clef_range "bass"
    ```

    <img width="350" height="200" alt="image" src="https://github.com/user-attachments/assets/c1e147d3-7a81-457b-8417-d9381daf4a53" />

    NOTE: Apple's security settings may flag the executable and not allow execution. To bypass this setting, run:

    ```
    chmod +x main
    ```

    Then go to System Settings > Privacy & Security, and scroll down to the Security section to allow the file to run.

     

## Executing Program (Git)

* From the root directory, run:
  ```
  python main.py --filepath [PATH/TO/MIDI/FILE] --clef_range ["bass" OR "treble"] --musescore_path [PATH/TO/MUSESCORE/EXECUTABLE]
  ```
  * `--filepath` is a required argument followed by the path to the processed MIDI file.
  * `--clef_range` is an optional argument followed by "bass" or "treble" to describe the clef range of the input file. Including this argument will output
  the tessituragram analysis of the MIDI file in both treble and bass clef range. If omitted, Tessituragram processes the file as is.
  * `--musescore_path` is an optional argument followed by the path to the MuseScore executable on your machine (`'C:\\Program Files\\MuseScore 4\\bin\\MuseScore4.exe'`, for example). The program searches for MuseScore installation by default, and this should only apply if the MuseScore path cannot be found by Tessituragram. The program will still run without Musescore installation but will not provide score visualization in the output PDF.
 
* Example:
  ```
  python main.py --filepath "data\test_data_arias\1-I.mid" --clef_range "bass"
  ```
  <img width="350" height="300" alt="image" src="https://github.com/user-attachments/assets/7aace345-5867-4c83-b3a1-268874781436" />

* The Git installation method also includes testing functions. To reproduce the results from the 150 musical composition, run
  ```
  python "tests\system_tests\get_stats.py"
  ```
  * This will pull in the musical compositions listed in the `data\test_data_arias` folder, process them, and compare the output to the manually analyzed data at `tests\system_tests\Master Data Calculation.xlsx`. Tessituragram produces an output file named `results.csv` that users can open using Microsoft Excel.
 
* Run `pytest` to execute unit tests for each function in the project.

## PDF Visualization

* The program will also return PDF outputs to a results folder within the project. The PDF has the same tessituragram information printed to the console as well as images that visualize the tessitura range. For score visualization in output PDFs, users must install [MuseScore](https://musescore.org/en/download).

  <img width="600" height="200" alt="image" src="https://github.com/user-attachments/assets/eaa49cac-3bca-4995-8fc8-99a0fdb5c155" />
  <br>
  <img width="300" height="450" alt="image" src="https://github.com/user-attachments/assets/1164c85b-fe54-48c5-b77f-d948df240b0a" />


## Creating Data

  * We have provided a test suite of 150 manually-verified vocal compositions at "data/test_data_arias". If using your own MIDI files, the data must meet the following conditions:
    * MIDI file must end with the extension `.mid` or `.midi`.
    * MIDI file must be a single track without added for instruments or multiple voices.
    * If there is a rest at the end of the composition, add a C1 pitch to the composition in an extra measure. Otherwise, any rests after the vocal line conclude in the composition will not register in the program.
  * Users can create MIDI files using free software. We used [MuseScore Studio](https://musescore.org/en)

## Lyric classification (optional)

`songfeat`'s `lyrics` feature group reads a song's words and reports what it is about:
themes, tone, content advisories, how strongly the narrator's and the beloved's gender are
cast, and subjects a particular student may need to avoid. It is the one group that is not
offline, because it asks a classification model.

**Everything else works without it.** No key, no network, no cost — and the `lyrics` columns
report null with a reason saying the key is absent. Adding the key enables one feature group;
it is not a prerequisite for running anything.

To enable it, copy `.env.example` to `.env` and set `JEV_KEY` to a TypeSafe API key. Then ask
for the group:

```bash
venv/bin/python -m songfeat scores/ --groups lyrics -o library.csv
```

**What it costs.** Under three cents per hundred songs: about 153 questions per song in 8
batched calls, billed on input tokens only. Answers are cached per question, so a re-run of
unchanged files costs nothing. To price a run before making it:

```bash
venv/bin/python -m songfeat scores/ --groups lyrics --lyrics-estimate
```

While developing, `--lyrics-questions core` asks 13 questions instead of 153 — one call per
song, about 8% of the cost — and `--lyrics-max-calls N` stops a run rather than overspending if
a glob matched more than you meant.

**Lyrics must be in the file.** MIDI carries no words, so every column in this group is null on
a MIDI input. MusicXML, which carries `<lyric>` elements, is what this group needs.

## Help

Report any issues in the GitHub repo or reach out at [contact@tessituragram.com](contact@tessituragram.com)

## Authors

Troy Conklin

Paul M. Patinka

## Version History

* 0.1
    * Initial Release

## License

This project is licensed under the MIT License - see the LICENSE file for details



