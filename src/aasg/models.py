"""Strict configuration and semantic metadata models."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProjectConfig(StrictModel):
    artifact_root: str = "artifacts"
    run_log_root: str = "artifacts/aasg/runs"
    default_timeout_seconds: int = Field(default=90, gt=0)


class DirectInstrumentationConfig(StrictModel):
    application_id: str
    test_application_id: str
    runner: str
    app_apk: str
    test_apk: str
    device_output_dir: str

    @model_validator(mode="after")
    def safe_device_output_dir(self) -> DirectInstrumentationConfig:
        path = self.device_output_dir
        if not path.startswith("/") or path == "/" or ".." in path.split("/"):
            raise ValueError("device_output_dir must be a safe absolute device path")
        return self


class AndroidConfig(StrictModel):
    min_api: int = Field(default=33, ge=1)
    adb: str = "adb"
    gradle_wrapper: str = "./gradlew"
    prepare_tasks: list[str] = Field(default_factory=list)
    test_task: str
    additional_output_dir: str
    locale_argument: str
    theme_argument: str
    direct_instrumentation: DirectInstrumentationConfig | None = None


class VariantsConfig(StrictModel):
    locales: dict[str, str]
    themes: dict[str, str]
    groups: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def non_empty(self) -> VariantsConfig:
        if not self.locales or not self.themes:
            raise ValueError("variants.locales and variants.themes must not be empty")
        return self


class RenditionConfig(StrictModel):
    publish: str
    pipeline: str


class ArtifactConfig(StrictModel):
    id: str
    type: Literal["image", "video", "json"]
    source: str
    publish: str
    metadata: str | None = None
    renditions: list[RenditionConfig] = Field(default_factory=list)


NavigationMode = Literal["gestural", "three-button"]
NavigationPolicy = Literal["gestural", "three-button", "all", "ignore"]


class CaptureConfig(StrictModel):
    label: str
    test: str
    arguments: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = Field(default=None, gt=0)
    locales: list[str] | None = None
    themes: list[str] | None = None
    navigation: NavigationPolicy = "ignore"
    artifacts: list[ArtifactConfig]


class ResizeStep(StrictModel):
    type: Literal["resize"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fit: Literal["contain", "cover", "stretch"] = "contain"


class CropStep(StrictModel):
    type: Literal["crop"]
    x: int | None = Field(default=None, ge=0)
    y: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    region: str | None = None
    padding: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def exactly_one_source(self) -> CropStep:
        literal = all(value is not None for value in (self.x, self.y, self.width, self.height))
        if literal == (self.region is not None):
            raise ValueError("crop needs either x/y/width/height or region")
        return self


class PadStep(StrictModel):
    type: Literal["pad"]
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    color: str = "#00000000"


class BackgroundStep(StrictModel):
    type: Literal["background"]
    color: str | dict[str, str]


class BlurStep(StrictModel):
    type: Literal["blur"]
    sigma: float = Field(default=10.0, gt=0)


class RedactStep(StrictModel):
    type: Literal["redact"]
    regions: list[str] = Field(min_length=1)
    mode: Literal["blur", "solid"] = "blur"
    sigma: float = Field(default=18.0, gt=0)
    color: str = "black"


class DeviceFrameStep(StrictModel):
    type: Literal["device_frame"]
    source: str
    frame: str
    fit: Literal["contain", "cover", "stretch"] = "cover"
    background: str | dict[str, str] | None = None
    crop_to_frame: bool = False

    @model_validator(mode="after")
    def safe_frame_id(self) -> DeviceFrameStep:
        parts = self.frame.split("/")
        if (
            not self.frame
            or self.frame.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError("device frame must be a contained relative ID")
        return self


class EdgeFadeStep(StrictModel):
    type: Literal["edge_fade"]
    edges: list[Literal["top", "right", "bottom", "left"]] = Field(min_length=1)
    pixels: int = Field(gt=0)


class FeatherStep(StrictModel):
    type: Literal["feather"]
    pixels: int = Field(gt=0)


class TrimStep(StrictModel):
    type: Literal["trim"]
    start_seconds: float = Field(default=0, ge=0)
    duration_seconds: float = Field(gt=0)


class TemporalFadeStep(StrictModel):
    type: Literal["temporal_fade"]
    in_seconds: float = Field(default=0, ge=0)
    out_seconds: float = Field(default=0, ge=0)


PipelineStep = Annotated[
    ResizeStep
    | CropStep
    | PadStep
    | BackgroundStep
    | BlurStep
    | RedactStep
    | DeviceFrameStep
    | EdgeFadeStep
    | FeatherStep
    | TrimStep
    | TemporalFadeStep,
    Field(discriminator="type"),
]


class PipelineConfig(StrictModel):
    steps: list[PipelineStep]
    frame_rate: int = Field(default=30, gt=0)
    crf: int = Field(default=18, ge=0, le=51)


class RemoteFrameSource(StrictModel):
    kind: Literal["device-frames-media"]
    index_url: str = (
        "https://raw.githubusercontent.com/jonnyjackson26/device-frames-media/"
        "main/device-frames-output/index.json"
    )
    allow_unlicensed_downloads: bool = False


class LocalFrameSource(StrictModel):
    kind: Literal["local"]
    root: str
    license: str


FrameSource = Annotated[RemoteFrameSource | LocalFrameSource, Field(discriminator="kind")]

CONFIG_SCHEMA_VERSION = 3


class AasgConfig(StrictModel):
    schema_version: Literal[3] = Field(alias="schema")
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    android: AndroidConfig
    variants: VariantsConfig
    captures: dict[str, CaptureConfig]
    pipelines: dict[str, PipelineConfig] = Field(default_factory=dict)
    frame_sources: dict[str, FrameSource] = Field(default_factory=dict)

    @model_validator(mode="after")
    def references_exist(self) -> AasgConfig:
        named_sections: dict[str, Mapping[str, object]] = {
            "locale": self.variants.locales,
            "theme": self.variants.themes,
            "group": self.variants.groups,
            "capture": self.captures,
            "pipeline": self.pipelines,
            "frame source": self.frame_sources,
        }
        for section, values in named_sections.items():
            for value in values:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
                    raise ValueError(f"{section} ID is not path-safe: {value!r}")
        for group, captures in self.variants.groups.items():
            unknown = set(captures) - self.captures.keys()
            if unknown:
                raise ValueError(f"group {group!r} references unknown captures: {sorted(unknown)}")
        for capture_id, capture in self.captures.items():
            for artifact in capture.artifacts:
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", artifact.id):
                    raise ValueError(
                        f"capture {capture_id!r} has a path-unsafe artifact ID: {artifact.id!r}"
                    )
            for locale in capture.locales or []:
                if locale not in self.variants.locales:
                    raise ValueError(f"capture {capture_id!r} references unknown locale {locale!r}")
            for theme in capture.themes or []:
                if theme not in self.variants.themes:
                    raise ValueError(f"capture {capture_id!r} references unknown theme {theme!r}")
            for artifact in capture.artifacts:
                if capture.navigation == "all":
                    navigation_paths = [artifact.publish]
                    navigation_paths.extend(rendition.publish for rendition in artifact.renditions)
                    if any("{navigation}" not in path for path in navigation_paths):
                        raise ValueError(
                            f"capture {capture_id!r} uses navigation 'all', so every publication "
                            "path must contain {navigation}"
                        )
                for rendition in artifact.renditions:
                    if rendition.pipeline not in self.pipelines:
                        raise ValueError(
                            f"artifact {artifact.id!r} references unknown pipeline "
                            f"{rendition.pipeline!r}"
                        )
        for pipeline_id, pipeline in self.pipelines.items():
            for step in pipeline.steps:
                if isinstance(step, DeviceFrameStep) and step.source not in self.frame_sources:
                    raise ValueError(
                        f"pipeline {pipeline_id!r} references unknown frame source {step.source!r}"
                    )
        return self


class Region(StrictModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SemanticMetadata(StrictModel):
    schema_version: Literal[1] = Field(alias="schema")
    media: str
    regions: dict[str, Region]


class FrameGeometry(StrictModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class FrameChecksums(StrictModel):
    frame: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    mask: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class FrameMetadata(StrictModel):
    frame: str
    mask: str
    screen: FrameGeometry
    frame_size: dict[str, int] = Field(alias="frameSize")
    hex_color: str | None = Field(default=None, alias="hexColor")
    sha256: FrameChecksums | None = None

    @model_validator(mode="after")
    def valid_frame_size(self) -> FrameMetadata:
        if set(self.frame_size) != {"width", "height"}:
            raise ValueError("frameSize must contain width and height")
        if any(value <= 0 for value in self.frame_size.values()):
            raise ValueError("frameSize values must be positive")
        return self
