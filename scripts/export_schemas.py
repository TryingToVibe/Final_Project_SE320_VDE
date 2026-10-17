"""Write JSON Schemas for the shared payloads to docs/schemas/ (hand these to Teams 4/7)."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from vde.models import CycleReport, DisposalEvent, ErrorResponse, SCHEMA_VERSION  # noqa: E402

out = pathlib.Path(__file__).resolve().parents[1] / "docs" / "schemas"
out.mkdir(parents=True, exist_ok=True)
for model in (CycleReport, DisposalEvent, ErrorResponse):
    schema = model.model_json_schema(mode="serialization")
    schema["$id"] = f"vde/{model.__name__}/{SCHEMA_VERSION}"
    (out / f"{model.__name__}.schema.json").write_text(json.dumps(schema, indent=2))
    print("wrote", model.__name__)
