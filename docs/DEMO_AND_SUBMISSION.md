# Demonstration and submission guide

## Demonstration sequence

1. Install the dependencies using the README, start `python web.py`, and open `http://127.0.0.1:8765`.
2. Confirm that the page reports the recognition backend is ready. A missing-backend notice means the face model cannot run yet.
3. Open Enrollment. Enter a unique resident ID, name and apartment, confirm consent, and capture/select 3–5 photos of the same person.
4. Save the resident and verify the resident directory displays their actual sample count.
5. Repeat for at least 20 distinct consenting people. A blank database is intentional; no identities are pre-filled or fabricated.
6. Open Live monitor, start the camera, and start recognition. Demonstrate a registered person receiving a green Entry ALLOWED decision.
7. Demonstrate an unregistered person receiving a red Entry REJECTED decision. A frame with no face must remain in the waiting state.
8. Check the entry history. Repeated frames are throttled to one event per identity every five seconds. These events are not a count of unique visitors.
9. Deactivate a resident and demonstrate that this identity no longer receives entry permission. If no active resident remains, monitoring requires enrollment/activation first.
10. Open Evaluation. Upload separate, held-out known-person and unknown-person photos, label their true identities and run evaluation. Download the measured report.

## What to explain

- OpenCV handles image decoding, resizing, camera frames and drawing.
- HOG detects face locations; dlib computes a 128-number embedding for each face.
- Each face is compared with every active resident's stored samples using Euclidean distance.
- A candidate is accepted only below the configured threshold and with sufficient separation from a different identity. Distances are not percentages.
- SQLite stores resident details, embeddings and entry events. Raw enrollment/test photos are not persisted by the browser server.
- Entry accuracy measures known-versus-unknown decisions. Identity accuracy also counts wrong-resident matches as errors. False positive rate uses unknown trials; false negative rate uses known trials.
- The threshold must be calibrated on validation data; final evaluation images must remain separate.

## Submission contents

- Source repository and README with exact run instructions.
- A working webcam demonstration and screenshots of actual allowed/rejected decisions.
- A private database containing at least 20 real registered identities, if the faculty requires the database itself. Do not publish biometric data in a public GitHub repository.
- The measured evaluation report, describing test-set size, conditions, accuracy and error rates.
- An explanation of limitations: lighting/pose sensitivity, possible false matches, no liveness detection and no physical gate control.

## Completion boundaries

Automated tests validate software behavior using controlled encodings. A successful test suite does not establish model accuracy. The 20-person deliverable and measured performance require actual enrollment and held-out data. Do not describe them as completed before collecting and evaluating those data.
