"""Validated public input contracts. Coordinates always refer to source pixels."""
import math
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator


class HistoryExportRow(BaseModel):
    model_config = {'extra': 'forbid'}
    run_id: str = Field(pattern=r'^[0-9a-f]{12}$')
    candidate_index: int = Field(ge=0)


class HistoryExportSelection(BaseModel):
    model_config = {'extra': 'forbid'}
    rows: list[HistoryExportRow] | None = None


class Region(BaseModel):
    text: str = ""
    polygon: list[tuple[float, float]]
    language: str = "en"
    ignore: bool = False

    @field_validator("polygon")
    @classmethod
    def valid_polygon(cls, value):
        from shapely.geometry import Polygon
        if len(value) < 3 or len(value) > 32 or any(not math.isfinite(n) or n < 0 for p in value for n in p):
            raise ValueError("Use 3–32 finite non-negative source-image points")
        p = Polygon(value)
        if not p.is_valid or p.area <= 0:
            raise ValueError("Polygon must have positive area and cannot self-intersect")
        return value


class Label(BaseModel):
    text: str = Field(min_length=1)
    present: bool = True
    polygon: list[tuple[float, float]] | None = None
    case_sensitive: bool = True
    min_confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("polygon")
    @classmethod
    def valid_polygon(cls, value):
        return Region.valid_polygon(value) if value is not None else None


class ValueField(BaseModel):
    name: str = Field(min_length=1)
    polygon: list[tuple[float, float]]
    expected: str | None = None
    parser: Literal["text", "number"] = "text"
    decimal_separator: Literal[".", ","] = "."

    @field_validator("polygon")
    @classmethod
    def valid_polygon(cls, value):
        return Region.valid_polygon(value)


class Annotation(BaseModel):
    reviewed: bool = False
    complete: bool = False
    granularity: Literal["line", "word"] = "line"
    regions: list[Region] = []
    labels: list[Label] = []
    fields: list[ValueField] = []
    notes: str = ""


class EngineConfig(BaseModel):
    engine: Literal["rapidocr", "paddleocr", "easyocr", "tesseract"]
    device: Literal["cpu", "gpu"] = "cpu"
    languages: list[str] = Field(default_factory=lambda: ["en"], min_length=1, max_length=10)
    python_path: str | None = None
    threads: int = Field(default=4, ge=1, le=64)
    options: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_device(self):
        if self.engine == "tesseract" and self.device == "gpu":
            raise ValueError("Tesseract supports CPU only. Select CPU or use a GPU-capable OCR engine.")
        return self

    @field_validator("options")
    @classmethod
    def options_are_serializable(cls, value):
        import json
        if len(json.dumps(value, allow_nan=False)) > 16000:
            raise ValueError("Engine options too large")
        return value


class RunConfig(BaseModel):
    samples: list[str] = Field(default_factory=lambda: ["pivi-pro"], max_length=500)
    engines: list[EngineConfig] = Field(default_factory=lambda: [EngineConfig(engine="rapidocr")], min_length=1, max_length=12)
    mode: Literal["saved", "replay", "live"] = "saved"
    preprocessing: Literal["raw", "upscale", "contrast", "sharpen"] = "raw"
    track: Literal["full", "known_crops"] = "full"
    warmups: int = Field(default=1, ge=0, le=20)
    repetitions: int = Field(default=3, ge=1, le=100)
    timeout_s: float = Field(default=120, ge=1, le=600)
    iou_threshold: float = Field(default=0.5, gt=0, le=1)
    replay_fps: float = Field(default=2, gt=0, le=120)
    replay_offsets_ms: list[float] | None = None
    queue_policy: Literal["all", "latest"] = "latest"
    queue_size: int = Field(default=2, ge=1, le=120)
    camera_index: int = Field(default=0, ge=0, le=20)
    duration_s: float = Field(default=10, ge=1, le=300)
    camera_width: int = Field(default=1280, ge=160, le=7680)
    camera_height: int = Field(default=720, ge=120, le=4320)
    save_camera_frames: bool = False
    max_p95_ms: float | None = Field(default=None, gt=0)
    min_e2e_f1: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def check_run(self):
        if self.mode != "live" and not self.samples:
            raise ValueError("Select at least one image")
        if self.mode == "live" and (len(self.engines) != 1 or self.track != "full"):
            raise ValueError("Live capture requires one engine and the full-image track")
        if self.replay_offsets_ms is not None:
            if len(self.replay_offsets_ms) != len(self.samples) or any(not math.isfinite(n) or n < 0 for n in self.replay_offsets_ms):
                raise ValueError("Replay offsets must match samples and be finite, non-negative milliseconds")
            if sorted(self.replay_offsets_ms) != self.replay_offsets_ms:
                raise ValueError("Replay offsets must be ordered")
        if self.mode != "saved" and self.track != "full":
            raise ValueError("Known-crop recognition uses saved images")
        return self
