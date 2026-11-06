"""The few JSON Schema keywords our extraction schema uses (no third-party dependency)."""


def errors(value, schema, path="$") -> list[str]:
    if "oneOf" in schema:
        matching = sum(1 for option in schema["oneOf"] if not errors(value, option, path))
        return [] if matching == 1 else [f"{path}: matches {matching} of the oneOf options"]
    if "enum" in schema:
        return [] if value in schema["enum"] else [f"{path}: {value!r} not in {schema['enum']}"]
    kind = schema.get("type")
    checks = {"object": dict, "array": list, "string": str, "integer": int}
    if kind not in checks or not isinstance(value, checks[kind]) or isinstance(value, bool):
        return [f"{path}: expected {kind}"]
    found = []
    if kind == "object":
        found += [f"{path}.{k}: required" for k in schema.get("required", []) if k not in value]
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                found += errors(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                found.append(f"{path}.{key}: not allowed")
    if kind == "array":
        for i, item in enumerate(value):
            found += errors(item, schema["items"], f"{path}[{i}]")
    return found
