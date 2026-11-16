"""OpenCV webcam capture and dlib face encoding, loaded only for vision commands."""
import time
import cv2
import face_recognition


def faces(frame):
    height, width = frame.shape[:2]
    scale = min(1.0, 640 / width)
    resized = cv2.resize(frame, (int(width*scale), int(height*scale)))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb, model='hog')
    encodings = face_recognition.face_encodings(rgb, locations, model='small')
    return [(tuple(int(v/scale) for v in box), enc) for box, enc in zip(locations, encodings)]


def image_encoding(path):
    frame = cv2.imread(str(path))
    if frame is None:
        raise ValueError('Could not read image: ' + str(path))
    detected = faces(frame)
    if len(detected) != 1:
        raise ValueError(f'{path}: expected exactly one face; found {len(detected)}')
    return detected[0][1].tolist()


def validate_samples(samples):
    """Reject mixed-person enrollment instead of poisoning a resident's gallery."""
    if not samples:
        raise ValueError('No valid enrollment samples captured.')
    for sample in samples[1:]:
        if float(face_recognition.face_distance([samples[0]], sample)[0]) > 0.50:
            raise ValueError('Samples are inconsistent. Use clear photos of the same person and retry.')
    return samples


def camera(index):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        raise ValueError('Cannot open webcam. Check camera permissions or try --camera 1.')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
    return cap


def capture(index, count):
    cap = camera(index)
    samples = []
    last = 0.0
    try:
        while len(samples) < count:
            ok, frame = cap.read()
            if not ok:
                raise ValueError('Camera disconnected.')
            detected = faces(frame)
            label = f'ENROLL {len(samples)}/{count} | Look forward, then turn slightly | Q cancels'
            color = (80, 210, 100) if len(detected) == 1 else (60, 80, 255)
            if len(detected) == 1:
                (top,right,bottom,left), enc = detected[0]
                cv2.rectangle(frame, (left,top), (right,bottom), color, 2)
                crop = frame[max(0,top):bottom, max(0,left):right]
                clear = (right-left >= 80 and bottom-top >= 80 and crop.size > 0
                         and cv2.Laplacian(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var() >= 45)
                consistent = not samples or float(face_recognition.face_distance([samples[0]],enc)[0]) <= 0.50
                if not clear:
                    label = 'Move closer and hold still; face is too small or blurry'
                elif not consistent:
                    label = 'Different/inconsistent face: keep the same person in view'
                elif time.monotonic()-last >= 0.8:
                    samples.append(enc.tolist())
                    last = time.monotonic()
            else:
                label = 'Show exactly ONE face | ' + label
            cv2.rectangle(frame,(0,0),(frame.shape[1],65),(25,25,25),-1)
            cv2.putText(frame,label,(12,35),cv2.FONT_HERSHEY_SIMPLEX,0.48,color,1)
            cv2.imshow('Smart Society | Enrollment',frame)
            if cv2.waitKey(1) & 0xFF == ord('q') or cv2.getWindowProperty('Smart Society | Enrollment',cv2.WND_PROP_VISIBLE) < 1:
                raise ValueError('Enrollment cancelled; no samples saved.')
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return validate_samples(samples)


def monitor(db, index, threshold):
    from .core import match
    gallery = db.gallery()
    if not gallery:
        raise ValueError('Register at least one active resident first.')
    cap = camera(index)
    logged = {}
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                raise ValueError('Camera disconnected.')
            detected = faces(frame)
            for (top,right,bottom,left), enc in detected:
                result = match(enc, gallery, threshold)
                allowed = result['decision'] == 'ALLOWED'
                color = (60,220,100) if allowed else (60,60,255)
                label = f"Entry {result['decision']} | {result['name']}"
                cv2.rectangle(frame,(left,top),(right,bottom),color,2)
                cv2.rectangle(frame,(left,max(65,top-30)),(max(right,left+270),max(95,top)),(20,20,20),-1)
                cv2.putText(frame,label,(left,max(85,top-8)),cv2.FONT_HERSHEY_SIMPLEX,0.55,color,2)
                key = result['resident_id'] or 'unknown'
                now = time.monotonic()
                if now-logged.get(key,-100) >= 5:
                    db.log(result)
                    logged[key] = now
            cv2.rectangle(frame,(0,0),(frame.shape[1],55),(24,29,39),-1)
            status = 'SCAN ACTIVE' if detected else 'WAITING FOR FACE | No entry decision'
            cv2.putText(frame,status+' | Q: stop',(15,35),cv2.FONT_HERSHEY_SIMPLEX,0.6,(240,240,240),1)
            cv2.imshow('Smart Society | Live Entry Monitor',frame)
            if cv2.waitKey(1) & 0xFF == ord('q') or cv2.getWindowProperty('Smart Society | Live Entry Monitor',cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
