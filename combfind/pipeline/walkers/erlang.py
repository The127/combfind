class ErlangWalker:
    def extract_symbols(self, root, module_name: str) -> list[dict]:
        results: list[dict] = []
        seen_fns: set[str] = set()
        children = root.children
        for i, node in enumerate(children):
            doc = _preceding_doc(children, i)
            if node.type == "fun_decl":
                _extract_function(node, module_name, doc, seen_fns, results)
            elif node.type == "type_alias":
                _extract_type(node, module_name, doc, results)
            elif node.type == "record_decl":
                _extract_record(node, module_name, doc, results)
        return results

    def extract_skeleton(self, source: str, kind: str) -> str:
        return source


def _preceding_doc(children: list, idx: int) -> str | None:
    if idx == 0:
        return None
    prev = children[idx - 1]
    if prev.type != "comment":
        return None
    text = prev.text.decode("utf-8", errors="replace")
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip("% ").strip()
        if stripped.startswith("@doc"):
            stripped = stripped[4:].strip()
        if stripped:
            lines.append(stripped)
    return " ".join(lines) if lines else None


def _extract_function(node, module_name: str, doc: str | None, seen: set, results: list) -> None:
    fc = next((c for c in node.children if c.type == "function_clause"), None)
    if fc is None:
        return
    name_node = next((c for c in fc.children if c.type == "atom"), None)
    if name_node is None:
        return
    name = name_node.text.decode("utf-8")
    if name in seen:
        return
    seen.add(name)

    args_node = next((c for c in fc.children if c.type == "expr_args"), None)
    args_text = args_node.text.decode("utf-8") if args_node else "()"
    results.append({
        "name": name,
        "qualified_name": f"{module_name}.{name}",
        "kind": "function",
        "signature": f"{name}{args_text}",
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "docstring": doc,
    })


def _extract_type(node, module_name: str, doc: str | None, results: list) -> None:
    type_name_node = next((c for c in node.children if c.type == "type_name"), None)
    if type_name_node is None:
        return
    atom = next((c for c in type_name_node.children if c.type == "atom"), None)
    if atom is None:
        return
    name = atom.text.decode("utf-8")
    results.append({
        "name": name,
        "qualified_name": f"{module_name}.{name}",
        "kind": "type_alias",
        "signature": f"-type {name}()",
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "docstring": doc,
    })


def _extract_record(node, module_name: str, doc: str | None, results: list) -> None:
    atom = next((c for c in node.children if c.type == "atom"), None)
    if atom is None:
        return
    name = atom.text.decode("utf-8")
    results.append({
        "name": name,
        "qualified_name": f"{module_name}.{name}",
        "kind": "record",
        "signature": f"-record({name}, ...)",
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "docstring": doc,
    })
