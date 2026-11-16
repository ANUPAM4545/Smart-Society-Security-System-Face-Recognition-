# How the Smart Society Security System Is Built

The project uses a laptop camera to compare a person's face with registered residents. It displays **Entry ALLOWED in green** when a resident is recognized and **Entry REJECTED in red** for an unknown or ambiguous face. The result is a screen decision; no physical gate is connected.

## Technologies

| Technology | Purpose |
| --- | --- |
| Python | Application logic, local HTTP server and evaluation |
| OpenCV | Image decoding, resizing, camera capture and visual overlays |
| face_recognition / dlib | HOG face detection and 128-dimensional face embeddings |
| SQLite | Local storage for residents, face embeddings and entry events |
| HTML and CSS | Browser dashboard layout and styling |
| JavaScript | Browser camera access, photo capture, API requests and report downloads |
| Tkinter | Alternative desktop control panel |
| unittest | Automated checks for matching, storage, reports and API behavior |

## Architecture

The browser runs the interface and obtains camera access through `getUserMedia`. It captures JPEG frames and sends them to a Python HTTP server on `127.0.0.1`. Python detects and encodes faces, compares them with the active residents in SQLite, and returns the decisions and face coordinates. JavaScript draws colored boxes and messages over the camera feed.

All recognition processing happens on the laptop. No external face-recognition API is used. The browser server stores embeddings and event records; it does not save the raw enrollment photos or camera video.

## Project structure

| File | Responsibility |
| --- | --- |
| `web.py` | Local HTTP server, browser API endpoints and static asset delivery |
| `web/index.html` | Dashboard pages, forms, tables and camera containers |
| `web/style.css` | Dashboard appearance and responsive layout |
| `web/app.js` | Camera state, enrollment, live recognition, resident controls and evaluation UI |
| `security/vision.py` | Image processing, face detection, embeddings and desktop camera loops |
| `security/core.py` | SQLite operations, nearest-face matching and metric calculations |
| `security/evaluation.py` | Shared report construction, Markdown formatting and report saving |
| `main.py` | Command-line enrollment, monitoring, resident management, logs and evaluation |
| `app.py` | Desktop interface that runs CLI operations in child processes |
| `tests/` | Automated matching, database, report and HTTP handler tests |

## Resident enrollment

A resident is registered with a unique ID, name, apartment and several face samples. In the browser, the user confirms consent and captures or selects three to five photos.

Each image must contain exactly one detectable face. The face model converts it into 128 numbers describing its visual features. Samples are checked against the first sample: distances above 0.50 are rejected as inconsistent. Only after all samples pass are the resident and embeddings saved together in SQLite.

Additional samples can be added using the same resident ID and matching name/apartment. Conflicting details for an existing ID are rejected. Changing resident details in the browser clears pending samples to reduce accidental enrollment under the wrong identity.

## Face detection and recognition

1. OpenCV resizes the frame to at most 640 pixels wide and converts BGR pixels to RGB.
2. The HOG detector locates faces. dlib generates an embedding for each detected face.
3. The application calculates Euclidean distance from that embedding to every stored sample belonging to an active resident.
4. It keeps the smallest distance for each resident and ranks the residents by distance.
5. The nearest resident is accepted when the distance is at most the configured threshold, 0.48 by default, and is separated from the next closest resident by at least 0.04.
6. Faces above the threshold or too close to two different identities are rejected. No detected face produces a waiting state rather than an entry decision.

Distance is a similarity measure, not a confidence percentage. The threshold is configurable because lighting, pose and image quality can affect results.

## Database design

The local database is created automatically at `data/society.db`.

| Table | Stored fields | Relationship |
| --- | --- | --- |
| `residents` | ID, name, apartment, active status and creation time |
| `encodings` | Sample ID, resident ID and a JSON face vector | Multiple samples belong to one resident |
| `events` | Event ID, UTC timestamp, resident ID, decision, distance and reason | Recognized events reference a resident; unknown events use a null resident ID |

Foreign keys keep references consistent. Parameterized SQL is used for data operations. Deactivating a resident excludes their samples from recognition without deleting their details or history.

## Entry decisions and logging

Each detected face is evaluated independently. A recognized resident appears in green; an unknown or ambiguous face appears in red. The Python server records the decision with a timestamp and matching distance.

A five-second cooldown limits repeated event rows for the same identity. Unknown faces share one cooldown. These records represent detection events, not a count of unique people. The dashboard shows the total event count and the most recent 100 entries, which can be exported to CSV.

## Browser API

| Endpoint | Operation |
| --- | --- |
| `GET /api/status` | Read backend readiness, residents, enrollment count and recent events |
| `POST /api/enroll` | Validate enrollment photos and save a resident's face samples |
| `POST /api/recognize` | Process a frame, return decisions and log entry events |
| `POST /api/resident-status` | Activate or deactivate a resident |
| `POST /api/evaluate` | Evaluate labeled test images and generate measured reports |

The server binds to loopback only, validates Host and Origin headers, limits request sizes, and accepts JSON for write operations. Missing vision dependencies are reported explicitly. These controls support local use; the app is not designed as a publicly hosted access-control service.

## Evaluation and reports

The browser accepts up to 30 labeled test images per evaluation. Each known person is labeled with their registered ID; an unregistered person is labeled as an unknown visitor. The CLI supports a CSV containing image paths and expected IDs.

The application compares predicted identities with the supplied labels and calculates:

- Entry accuracy: correct known-versus-unknown entry decisions divided by all trials.
- Identity accuracy: exact identity predictions, including correct unknown rejections, divided by all trials.
- False positives: unknown visitors accepted as residents.
- False negatives: registered residents rejected.
- False positive rate and false negative rate, using the corresponding unknown and known trial counts.
- Wrong-resident matches, reported separately and counted as errors in identity accuracy.

Reports are written to `reports/evaluation.json` and `reports/evaluation.md`; browser users can also download them. Evaluation does not create entry log events. Test images must be separate from enrollment and threshold-tuning images. Actual accuracy depends on those measured trials and is not fabricated by the application.

## Testing and limitations

The automated tests cover distance thresholds, unknown and ambiguous faces, SQLite persistence, resident deactivation, 20-ID storage capacity, event throttling, report calculations, malformed input and API workflows. API tests use controlled embeddings so application behavior can be checked without a camera or installed face model. They do not measure real-world face-recognition accuracy.

The system has no liveness detection, so photographs may fool it. It can also make errors under difficult lighting or poses. The SQLite database is not encrypted by the application. Real resident enrollment and held-out camera testing are necessary to demonstrate the assignment's 20-person database and measured performance.
