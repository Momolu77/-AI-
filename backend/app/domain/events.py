"""Versioned event contracts. The shared JSON registry also generates browser validators."""

import json
from typing import Annotated, Literal, Union

from pydantic import Field, create_model

from app.domain.legacy_events import Id, Nonnegative, StrictModel, parse_time
from app.domain.legacy_events import validate_payload as validate_legacy
from app.settings import ROOT

CONTRACT = json.loads((ROOT / "config/events-v1.3.json").read_text(encoding="utf-8"))
PREVIOUS_CONTRACT = json.loads(
    (ROOT / "config/events-v1.3-20261009.json").read_text(encoding="utf-8")
)
SCHEMA_VERSION = CONTRACT["schema_version"]
LEGACY_VERSION = "teaching-workbench-events-v1.1"
DEFINITIONS = {}


def field_type(spec):
    if isinstance(spec, str):
        primitives = {
            "str": str,
            "time": str,
            "id": Id,
            "nat": Nonnegative,
            "positive": Annotated[int, Field(ge=1)],
            "number": float,
            "nonnegative": Annotated[float, Field(ge=0)],
            "bool": bool,
        }
        return primitives[spec] if spec in primitives else DEFINITIONS[spec]
    if "nullable" in spec:
        return field_type(spec["nullable"]) | None
    if "array" in spec:
        return list[field_type(spec["array"])]
    if "enum" in spec:
        return Literal[tuple(spec["enum"])]
    if "union" in spec:
        return Union[tuple(field_type(t) for t in spec["union"])]
    return create_model(
        "Object",
        __base__=StrictModel,
        **{k: (field_type(v), ...) for k, v in spec["object"].items()},
    )


for name, definition in CONTRACT["definitions"].items():
    DEFINITIONS[name] = field_type(definition)
FIELDS = {
    name: {key: field_type(value) for key, value in spec["fields"].items()}
    for name, spec in CONTRACT["events"].items()
}
REGISTRY = {
    name: create_model(
        name, __base__=StrictModel, **{key: (typ, ...) for key, typ in fields.items()}
    )
    for name, fields in FIELDS.items()
}
SYSTEM_EVENTS = {name for name, spec in CONTRACT["events"].items() if spec["actor"] == "system"}
SERVICE_EVENTS = {name for name, spec in CONTRACT["events"].items() if spec["owner"] != "browser"}


def validate_payload(name, payload, schema_version=SCHEMA_VERSION, *, historical=False):
    if schema_version == LEGACY_VERSION:
        return validate_legacy(name, payload)
    if schema_version != SCHEMA_VERSION or name not in REGISTRY:
        raise ValueError("未知事件或 schema 版本")
    if historical and name == "resource_reference_added" and "reference_purpose" not in payload:
        model = create_model(
            "HistoricalReference",
            __base__=StrictModel,
            **{
                k: (field_type(v), ...)
                for k, v in PREVIOUS_CONTRACT["events"][name]["fields"].items()
            },
        )
        result = model.model_validate(payload).model_dump()
    else:
        result = REGISTRY[name].model_validate(payload).model_dump()
    if "edit_started_at" in result and parse_time(result["edit_started_at"]) > parse_time(
        result["last_edit_at"]
    ):
        raise ValueError("编辑起止时间不合法")
    for key in ("completed_at", "displayed_at"):
        if key in result:
            parse_time(result[key])

    def check_ranges(value):
        if isinstance(value, dict):
            if set(value) == {"start", "end"} and value["end"] < value["start"]:
                raise ValueError("范围结束不能小于开始")
            for item in value.values():
                check_ranges(item)
        elif isinstance(value, list):
            for item in value:
                check_ranges(item)

    check_ranges(result)
    return result


class Transport(StrictModel):
    producer_id: Id
    producer_seq: Annotated[int, Field(ge=1)]
    raw_time: str | None
    monotonic_ms: Annotated[float, Field(ge=0)] | None
    clock_calibration_id: Id | None
    time_source: Literal["client_clock", "iframe_clock", "server_clock", "unknown_legacy"]
    action_id: Id | None = None
    causal_parent_ids: list[Id] = Field(default_factory=list)
    client_sequence_no: Annotated[int, Field(ge=1)] | None = None


class ClientEvent(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    event_id: Id
    event_name: str
    actor: Literal["student", "system"]
    occurred_at: str
    client_sequence_no: Annotated[int, Field(ge=1)] | None = None
    transport: Transport
    payload: dict
