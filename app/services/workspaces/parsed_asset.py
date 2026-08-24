"""Stable parsed representation shared by Workspace asset parsers."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ParsedAsset:
    asset_id: str
    media_type: str
    parser_name: str
    parser_version: str
    segments: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        """Normalize IDs once after a parser has produced all segments."""

        normalized = []
        for index, raw_segment in enumerate(self.segments, start=1):
            segment = dict(raw_segment)
            segment["segment_id"] = f"s{index:06d}"
            normalized.append(segment)
        object.__setattr__(self, "segments", tuple(normalized))

    def to_dict(self) -> dict[str, object]:
        text_chars = sum(len(str(segment["text"])) for segment in self.segments)
        return {
            "schema_version": 1,
            "asset_id": self.asset_id,
            "media_type": self.media_type,
            "parser": {"name": self.parser_name, "version": self.parser_version},
            "metadata": {
                "segment_count": len(self.segments),
                "character_count": text_chars,
            },
            "segments": list(self.segments),
        }

    @classmethod
    def validate_payload(cls, payload: Mapping[str, Any], asset_id: str) -> None:
        if payload.get("schema_version") != 1 or payload.get("asset_id") != asset_id:
            raise ValueError("Parsed asset identity or schema version is invalid")
        if not isinstance(payload.get("segments"), list):
            raise ValueError("Parsed asset segments must be an array")
        for segment in payload["segments"]:
            if not isinstance(segment, Mapping) or not isinstance(segment.get("text"), str):
                raise ValueError("Parsed asset segment is invalid")
