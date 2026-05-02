_TYPE_DECLS = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
}


class JavaWalker:
    def extract_symbols(self, root, module_name: str) -> list[dict]:
        results: list[dict] = []
        package = _package_name(root) or module_name
        _walk(root, package, type_stack=[], results=results)
        return results

    def extract_skeleton(self, source: str, kind: str) -> str:
        return source


def _walk(node, package: str, type_stack: list[str], results: list[dict]) -> None:
    if node.type in _TYPE_DECLS:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        kind = _type_kind(node.type)
        signature = _type_signature(node, kind, name)
        qualified = (
            ".".join([package] + type_stack + [name])
            if package
            else ".".join(type_stack + [name])
        )
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": kind,
                "signature": signature,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _javadoc(node),
            }
        )
        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.named_children:
                _walk(child, package, type_stack + [name], results)
        return

    if node.type in ("method_declaration", "constructor_declaration"):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        params_node = node.child_by_field_name("parameters")
        params_text = params_node.text.decode("utf-8") if params_node else "()"
        if node.type == "method_declaration":
            ret_node = node.child_by_field_name("type")
            ret_text = ret_node.text.decode("utf-8") if ret_node else "void"
            signature = f"{ret_text} {name}{params_text}"
            kind = "method"
        else:
            signature = f"{name}{params_text}"
            kind = "constructor"
        qualified = (
            ".".join([package] + type_stack + [name])
            if package
            else ".".join(type_stack + [name])
        )
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": kind,
                "signature": signature,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _javadoc(node),
            }
        )
        return

    if node.type == "enum_constant":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        qualified = (
            ".".join([package] + type_stack + [name])
            if package
            else ".".join(type_stack + [name])
        )
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": "enum_constant",
                "signature": name,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _javadoc(node),
            }
        )
        return

    for child in node.named_children:
        _walk(child, package, type_stack, results)


def _type_kind(node_type: str) -> str:
    return {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "record_declaration": "record",
    }[node_type]


def _type_signature(node, kind: str, name: str) -> str:
    if kind == "record":
        params_node = node.child_by_field_name("parameters")
        params_text = params_node.text.decode("utf-8") if params_node else "()"
        return f"record {name}{params_text}"
    parts = [f"{kind} {name}"]
    superclass = node.child_by_field_name("superclass")
    if superclass is not None:
        super_text = next(
            (
                c.text.decode("utf-8")
                for c in superclass.named_children
                if c.type == "type_identifier"
            ),
            superclass.text.decode("utf-8").lstrip("extends").strip(),
        )
        parts.append(f"extends {super_text}")
    interfaces = node.child_by_field_name("interfaces")
    if interfaces is not None:
        type_list = next(
            (c for c in interfaces.named_children if c.type == "type_list"), None
        )
        if type_list is not None:
            names = [c.text.decode("utf-8") for c in type_list.named_children]
            if names:
                keyword = "extends" if kind == "interface" else "implements"
                parts.append(f"{keyword} {', '.join(names)}")
    return " ".join(parts)


def _package_name(root) -> str | None:
    for child in root.named_children:
        if child.type != "package_declaration":
            continue
        for inner in child.named_children:
            if inner.type in ("scoped_identifier", "identifier"):
                return inner.text.decode("utf-8")
    return None


def _javadoc(node) -> str | None:
    parent = node.parent
    if parent is None:
        return None
    siblings = parent.named_children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), None)
    if idx is None or idx == 0:
        return None
    prev = siblings[idx - 1]
    if prev.type != "block_comment":
        return None
    text = prev.text.decode("utf-8")
    if not text.startswith("/**"):
        return None
    inner = text[3:-2] if text.endswith("*/") else text[3:]
    lines = []
    for line in inner.splitlines():
        line = line.strip().lstrip("*").strip()
        if line:
            lines.append(line)
    return " ".join(lines) if lines else None
