class GleamWalker:
    def extract_symbols(self, root, module_name: str) -> list[dict]:
        results: list[dict] = []
        children = root.children
        for i, node in enumerate(children):
            doc = _preceding_doc(children, i)
            if node.type == "function":
                _extract_function(node, module_name, doc, results)
            elif node.type in ("type_definition", "type_alias"):
                _extract_type(node, module_name, doc, results)
            elif node.type == "constant":
                _extract_constant(node, module_name, doc, results)
        return results

    def extract_skeleton(self, source: str, kind: str) -> str:
        return source


def _preceding_doc(children: list, idx: int) -> str | None:
    if idx == 0:
        return None
    prev = children[idx - 1]
    if prev.type != "statement_comment":
        return None
    lines = []
    for line in prev.text.decode("utf-8", errors="replace").splitlines():
        stripped = line.lstrip("/ ").strip()
        if stripped:
            lines.append(stripped)
    return " ".join(lines) if lines else None


def _is_pub(node) -> bool:
    return any(c.type == "visibility_modifier" for c in node.children)


def _extract_function(node, module_name: str, doc: str | None, results: list) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = name_node.text.decode("utf-8")

    params_node = next((c for c in node.children if c.type == "function_parameters"), None)
    params_text = params_node.text.decode("utf-8") if params_node else "()"

    return_text = ""
    for i, c in enumerate(node.children):
        if c.type == "->" and i + 1 < len(node.children):
            rt = node.children[i + 1]
            if rt.type == "type":
                return_text = f" -> {rt.text.decode('utf-8')}"
            break

    prefix = "pub fn " if _is_pub(node) else "fn "
    results.append({
        "name": name,
        "qualified_name": f"{module_name}.{name}",
        "kind": "function",
        "signature": f"{prefix}{name}{params_text}{return_text}",
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "docstring": doc,
    })


def _extract_type(node, module_name: str, doc: str | None, results: list) -> None:
    type_name_node = next((c for c in node.children if c.type == "type_name"), None)
    if type_name_node is None:
        return
    type_id = next((c for c in type_name_node.children if c.type == "type_identifier"), None)
    if type_id is None:
        return
    name = type_id.text.decode("utf-8")

    kind = "type_alias" if node.type == "type_alias" else "enum"
    prefix = "pub type " if _is_pub(node) else "type "
    results.append({
        "name": name,
        "qualified_name": f"{module_name}.{name}",
        "kind": kind,
        "signature": f"{prefix}{name}",
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "docstring": doc,
    })


def _extract_constant(node, module_name: str, doc: str | None, results: list) -> None:
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return
    name = name_node.text.decode("utf-8")

    prefix = "pub const " if _is_pub(node) else "const "
    results.append({
        "name": name,
        "qualified_name": f"{module_name}.{name}",
        "kind": "constant",
        "signature": f"{prefix}{name}",
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "docstring": doc,
    })
