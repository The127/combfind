class PythonWalker:
    def extract_symbols(self, root, module_name: str) -> list[dict]:
        results: list[dict] = []
        _walk(root, module_name, class_stack=[], results=results)
        return results


def _walk(node, module_name: str, class_stack: list[str], results: list[dict]) -> None:
    if node.type == "class_definition":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")

        bases_node = node.child_by_field_name("superclasses")
        bases_text = ""
        if bases_node:
            raw = bases_node.text.decode("utf-8")
            bases_text = raw.strip("()")

        signature = f"class {name}({bases_text})" if bases_text else f"class {name}"
        qualified = ".".join([module_name] + class_stack + [name])
        range_node = node.parent if node.parent and node.parent.type == "decorated_definition" else node
        body = node.child_by_field_name("body")
        results.append({
            "name": name,
            "qualified_name": qualified,
            "kind": "class",
            "signature": signature,
            "start_line": range_node.start_point[0] + 1,
            "end_line": range_node.end_point[0] + 1,
            "docstring": _docstring(body),
        })
        for child in node.named_children:
            _walk(child, module_name, class_stack + [name], results)
        return

    if node.type == "function_definition":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        params_node = node.child_by_field_name("parameters")
        params_text = params_node.text.decode("utf-8") if params_node else "()"

        is_async = node.children[0].type == "async"
        prefix = "async def " if is_async else "def "
        signature = f"{prefix}{name}{params_text}"

        kind = "function" if not class_stack else ("constructor" if name == "__init__" else "method")
        qualified = ".".join([module_name] + class_stack + [name])
        range_node = node.parent if node.parent and node.parent.type == "decorated_definition" else node
        body = node.child_by_field_name("body")
        results.append({
            "name": name,
            "qualified_name": qualified,
            "kind": kind,
            "signature": signature,
            "start_line": range_node.start_point[0] + 1,
            "end_line": range_node.end_point[0] + 1,
            "docstring": _docstring(body),
        })
        return

    for child in node.named_children:
        _walk(child, module_name, class_stack, results)


def _docstring(body_node) -> str | None:
    named = body_node.named_children if body_node else []
    if not named:
        return None
    first = named[0]
    if first.type != "expression_statement":
        return None
    nc = first.named_children
    if not nc or nc[0].type != "string":
        return None
    string_node = nc[0]
    content_node = next(
        (c for c in string_node.named_children if c.type == "string_content"), None
    )
    return content_node.text.decode("utf-8", errors="replace") if content_node else None
