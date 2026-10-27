"""RapidOCR worker for YiQu (PP-OCRv5 mobile, local only).

--prepare  load the models and check a blank image, then print {"ready": true}
--serve    print {"ready": true}, then answer one JSON line per request: {"image": "<png path>"}
"""
import argparse
import contextlib
import json
import sys
from pathlib import Path


def load_engine():
    # Library logging goes to stderr so stdout carries only protocol lines.
    with contextlib.redirect_stdout(sys.stderr):
        from rapidocr import RapidOCR, OCRVersion, ModelType
        return RapidOCR(params={
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
            "EngineConfig.onnxruntime.intra_op_num_threads": 4,
            "EngineConfig.onnxruntime.inter_op_num_threads": 2,
            "Global.log_level": "warning",
        })


def recognize(engine, path):
    with contextlib.redirect_stdout(sys.stderr):
        from PIL import Image
        path = Path(path)
        if not path.is_file():
            raise ValueError("Image not found")
        with Image.open(path) as image:
            width, height = image.size
        result = engine(str(path))
        lines = []
        if result.txts is not None:
            for text, box in zip(result.txts, result.boxes):
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                lines.append({
                    "text": text,
                    "x": max(0, min(xs) / width),
                    "y": max(0, min(ys) / height),
                    "width": min(1, (max(xs) - min(xs)) / width),
                    "height": min(1, (max(ys) - min(ys)) / height),
                })
    return {"text": "\n".join(line["text"] for line in lines), "lines": lines}


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--serve", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    engine = load_engine()
    if args.prepare:
        with contextlib.redirect_stdout(sys.stderr):
            import numpy as np
            result = engine(np.full((64, 256, 3), 255, dtype=np.uint8))
            if result.txts is not None and any(result.txts):
                raise RuntimeError("Blank image check failed")
        emit({"ready": True})
        return
    emit({"ready": True})
    for line in sys.stdin:
        try:
            emit(recognize(engine, json.loads(line)["image"]))
        except Exception as exc:
            # Never echo image content or paths back; the app only needs to know it failed.
            emit({"error": type(exc).__name__})


if __name__ == "__main__":
    main()
