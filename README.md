# Smart Society Security System

A local computer vision assignment prototype using Python, OpenCV, dlib face recognition and SQLite. A webcam window displays **Entry ALLOWED in green** for a recognized resident and **Entry REJECTED in red** for an unknown or ambiguous face.

## Setup

Use Python 3.10 or 3.11 in a virtual environment. The dlib dependency may require CMake and a C++ compiler. On macOS, install Xcode Command Line Tools (`xcode-select --install`) and CMake (`brew install cmake`) if missing. On Windows, dlib may require Visual Studio C++ Build Tools; WSL is another option.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows activation: `.venv\Scripts\activate`.

## Browser application

```sh
python web.py
```

Open **http://127.0.0.1:8765**. The server binds only to your laptop. It uses Python's standard library, so the dashboard and resident management can start without OpenCV. The page clearly marks recognition/enrollment unavailable until vision dependencies are installed. Start camera preview explicitly, then choose Start recognition. Frames are sent only to the local Python process.

Use Enroll resident to fill in details, confirm consent, capture 3–5 camera images or select JPEG/PNG photos, and save. Every image must contain exactly one face and the samples must be consistent. Changing resident details clears pending samples to prevent saving images under the wrong identity. The browser enrollment path uses face-count and identity checks; additional blur/face-size heuristics apply to desktop webcam enrollment. Resident access and logs use the same SQLite database as the desktop/CLI apps. The total event count is shown, with the most recent 100 events available in the history/export view.

The Evaluation tab accepts up to 30 held-out JPEG/PNG images. Choose the expected resident ID for each known person; leave unknown visitors labeled Unknown visitor. Confirm the images were not used in enrollment or tuning, then run evaluation. The app computes actual metrics, saves `reports/evaluation.json` and `reports/evaluation.md`, and provides download buttons. Evaluation never adds entry log events. Invalid/no-face/multiple-face trials abort without saving a partial new report. Include both known and unknown people; otherwise one error-rate denominator may be zero and is shown as N/A.

Camera access requires browser permission. Use localhost/127.0.0.1, rather than a remote HTTP address. The browser server has no public authentication and should remain loopback-only. Requests with foreign Host or Origin headers are rejected. Stop the server with Ctrl+C.

## Desktop application

```sh
python app.py
```

The desktop control panel has Enrollment, Live monitor, Residents, Entry logs, and Evaluation tabs. Confirm consent, fill in a resident's details, then enroll from the webcam or photos. Use Live monitor to start the camera window. The Stop button ends a running operation; Q in the camera window exits normally. Resident activation/deactivation is disabled while an operation is running. Operation output appears at the bottom of the app.

The UI uses Tkinter. If your Python distribution lacks it, install a Python distribution with Tk support (or `python3-tk` on Debian/Ubuntu). The command-line interface below remains available independently.

## Register residents

```sh
python main.py register --id R01 --name "Anupam Singh" --apartment A101
```

The camera captures five samples, 0.8 seconds apart. Show exactly one face, look forward and turn slightly. Q cancels without saving. Repeat with distinct IDs for at least **20 consenting people**. Multiple samples of one person do not count as multiple residents.

Webcam enrollment skips faces smaller than 80 pixels or visibly blurry crops (Laplacian variance below 45). Enrollment samples must be within distance 0.50 of the first sample. These are heuristic quality checks, not liveness detection. If good samples are rejected, improve lighting and use frontal photos.

Alternatively enroll from single-person photos:

```sh
python main.py register --id R02 --name "Resident Two" --apartment A102 --images /path/front.jpg /path/side.jpg
python main.py residents
```

Encodings and resident details are stored in `data/society.db`. Raw photos and video are not saved. Additional enrollment with the same ID/name/apartment adds samples. Different details for an existing ID are rejected.

## Live entry monitoring

```sh
python main.py monitor
python main.py monitor --camera 1 --threshold 0.48
```

Allow camera access for your terminal/Python application in OS settings. Q stops monitoring. Each visible face is evaluated independently. No face means no entry decision. The closest identity must pass the distance threshold and be separated from the second closest identity by at least 0.04. Distances are not probability or confidence percentages. Lower thresholds are stricter; calibrate using validation photos before final testing.

Entry events are stored with UTC timestamps and a five-second per-identity cooldown; unknown faces share one cooldown. These are detection events, not a reliable count of unique visitors. Restart the monitor after resident updates.

```sh
python main.py logs
python main.py logs --csv entry_logs.csv
python main.py deactivate R02
python main.py activate R02
```

## Measured accuracy report

Create a CSV in a private dataset folder with `image,expected_id` columns, for example:

```csv
image,expected_id
test_photos/resident_01_new_photo.jpg,R01
test_photos/unregistered_visitor.jpg,
```

Paths are relative to the CSV; use a registered ID for a known person and a blank expected ID for an unregistered visitor. Each image must contain exactly one face. Bad images abort evaluation rather than silently inflating accuracy. Do not reuse enrollment photos.

```sh
python main.py evaluate dataset/test_manifest.csv
```

This writes `reports/evaluation.json` and `reports/evaluation.md` containing entry accuracy, identity accuracy, false positives, false negatives, their rates, wrong-resident matches and per-image results. A zero denominator is reported as N/A/null. A wrong-resident acceptance counts as a binary known-person acceptance but is explicitly penalized in identity accuracy. Test both registered and unregistered people in different lighting, pose and distance conditions. No accuracy results or 20-person enrollment are claimed before real collection and evaluation.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests require only Python's standard library. They verify matching, rejection, ambiguity, persistence, deactivation, 20-ID capacity, report arithmetic, malformed CSV handling, and HTTP API flows. Browser API tests substitute deterministic face encodings for the vision library and do not open a network port. They cover enrollment → recognition → logging → deactivation, log throttling, failed enrollment rollback, evaluation report saving, input validation, and Host/Origin checks. They do not validate camera hardware, the browser layout, model installation, or real recognition accuracy.

## Assignment scope and limitations

This is an academic prototype with screen decisions; it does not operate a physical gate. It lacks liveness/anti-spoofing and must not be relied on for real access control. Printed photos can potentially pass. Obtain consent for enrollment, keep biometric data local, and do not commit the database, photos or logs to public GitHub. `.gitignore` excludes the default data/report/dataset directories. Restrict access to local files; SQLite is not encrypted by this app.

Architecture: webcam → OpenCV frame → HOG face detector → dlib 128-dimensional encoding → nearest active resident → threshold/ambiguity decision → colored overlay and SQLite event log.

Reference: https://face-recognition.readthedocs.io/en/latest/face_recognition.html
