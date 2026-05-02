class GoWalker:
    def extract_symbols(self, root, module_name: str) -> list[dict]:
        results: list[dict] = []

        package = module_name.split(".")[-1]
        pkg_node = next(
            (c for c in root.named_children if c.type == "package_clause"), None
        )
        if pkg_node:
            pkg_id = next(
                (c for c in pkg_node.named_children if c.type == "package_identifier"),
                None,
            )
            if pkg_id:
                package = pkg_id.text.decode("utf-8")

        for node in root.named_children:
            if node.type == "function_declaration":
                name_node = next(
                    (c for c in node.named_children if c.type == "identifier"), None
                )
                if name_node is None:
                    continue
                name = name_node.text.decode("utf-8")
                params = next(
                    (c for c in node.named_children if c.type == "parameter_list"), None
                )
                sig = f"func {name}{params.text.decode('utf-8') if params else '()'}"
                results.append(
                    {
                        "name": name,
                        "qualified_name": f"{package}.{name}",
                        "kind": "function",
                        "signature": sig,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "docstring": _docstring(node),
                    }
                )

            elif node.type == "method_declaration":
                recv_type = _receiver_type(node)
                name_node = next(
                    (c for c in node.named_children if c.type == "field_identifier"),
                    None,
                )
                if name_node is None:
                    continue
                name = name_node.text.decode("utf-8")
                param_lists = [
                    c for c in node.named_children if c.type == "parameter_list"
                ]
                params = param_lists[1] if len(param_lists) > 1 else None
                recv_str = param_lists[0].text.decode("utf-8") if param_lists else ""
                params_text = params.text.decode("utf-8") if params else "()"
                sig = f"func {recv_str} {name}{params_text}"
                qualified = (
                    f"{package}.{recv_type}.{name}"
                    if recv_type
                    else f"{package}.{name}"
                )
                results.append(
                    {
                        "name": name,
                        "qualified_name": qualified,
                        "kind": "method",
                        "signature": sig,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "docstring": _docstring(node),
                    }
                )

            elif node.type == "type_declaration":
                for spec in node.named_children:
                    if spec.type != "type_spec":
                        continue
                    name_node = next(
                        (c for c in spec.named_children if c.type == "type_identifier"),
                        None,
                    )
                    if name_node is None:
                        continue
                    name = name_node.text.decode("utf-8")
                    body = spec.named_children[-1] if spec.named_children else None
                    kind = (
                        "interface"
                        if (body and body.type == "interface_type")
                        else "struct"
                    )
                    results.append(
                        {
                            "name": name,
                            "qualified_name": f"{package}.{name}",
                            "kind": kind,
                            "signature": f"type {name} {kind}",
                            "start_line": node.start_point[0] + 1,
                            "end_line": node.end_point[0] + 1,
                            "docstring": _docstring(node),
                        }
                    )

        return results

    def extract_skeleton(self, source: str, kind: str) -> str:
        return source


def _docstring(node) -> str | None:
    parent = node.parent
    if parent is None:
        return None
    siblings = parent.named_children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), None)
    if idx is None or idx == 0:
        return None
    lines = []
    for sib in reversed(siblings[:idx]):
        if sib.type != "comment":
            break
        text = sib.text.decode("utf-8").strip()
        if text.startswith("//go:"):
            continue
        lines.append(text.lstrip("/ ").lstrip("* ").strip())
    return " ".join(reversed(lines)) if lines else None


def _receiver_type(method_node) -> str | None:
    recv = method_node.named_children[0]
    if recv.type != "parameter_list":
        return None
    for param in recv.named_children:
        for child in param.named_children:
            if child.type == "type_identifier":
                return child.text.decode("utf-8")
            if child.type == "pointer_type":
                inner = next(
                    (c for c in child.named_children if c.type == "type_identifier"),
                    None,
                )
                if inner:
                    return inner.text.decode("utf-8")
    return None
