_NAMED_CONTAINERS = {
    "class_declaration",
    "object_declaration",
}


class KotlinWalker:
    def extract_symbols(self, root, module_name: str) -> list[dict]:
        results: list[dict] = []
        package = _package_name(root) or module_name
        _walk(root, package, type_stack=[], results=results)
        return results

    def extract_skeleton(self, source: str, kind: str) -> str:
        return source


def _walk(node, package: str, type_stack: list[str], results: list[dict]) -> None:
    if node.type in _NAMED_CONTAINERS:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        kind = _container_kind(node)
        signature = _container_signature(node, kind, name)
        qualified = _qualify(package, type_stack, name)
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": kind,
                "signature": signature,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _kdoc(node),
            }
        )
        for body in _bodies(node):
            for child in body.named_children:
                _walk(child, package, type_stack + [name], results)
        return

    if node.type == "companion_object":
        # `companion object Foo {}` may have a named identifier; otherwise
        # the implicit name is "Companion" (per Kotlin spec).
        name = "Companion"
        for child in node.children:
            if child.type == "identifier":
                name = child.text.decode("utf-8")
                break
        qualified = _qualify(package, type_stack, name)
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": "class",
                "signature": f"companion object {name}",
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _kdoc(node),
            }
        )
        for body in _bodies(node):
            for child in body.named_children:
                _walk(child, package, type_stack + [name], results)
        return

    if node.type == "function_declaration":
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        signature = _function_signature(node, name)
        # A method lives inside a type_stack frame; a top-level function does
        # not. Kotlin extension functions are top-level too — the receiver
        # type is part of the signature, not the qualified name.
        kind = "method" if type_stack else "function"
        qualified = _qualify(package, type_stack, name)
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": kind,
                "signature": signature,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _kdoc(node),
            }
        )
        return

    if node.type == "property_declaration":
        name = _property_name(node)
        if name is None:
            return
        qualified = _qualify(package, type_stack, name)
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": _property_kind(node),
                "signature": _property_signature(node, name),
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _kdoc(node),
            }
        )
        return

    if node.type == "enum_entry":
        name_node = next((c for c in node.children if c.type == "identifier"), None)
        if name_node is None:
            return
        name = name_node.text.decode("utf-8")
        qualified = _qualify(package, type_stack, name)
        results.append(
            {
                "name": name,
                "qualified_name": qualified,
                "kind": "enum_constant",
                "signature": name,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": _kdoc(node),
            }
        )
        return

    for child in node.named_children:
        _walk(child, package, type_stack, results)


def _qualify(package: str, type_stack: list[str], name: str) -> str:
    parts = ([package] if package else []) + type_stack + [name]
    return ".".join(parts)


def _container_kind(node) -> str:
    if node.type == "object_declaration":
        return "class"
    # class_declaration covers class / interface / enum class / annotation
    # class / data class / sealed class. The keyword child distinguishes
    # interface; modifiers carry enum / data / annotation.
    keyword = next(
        (c for c in node.children if c.type in ("class", "interface")),
        None,
    )
    if keyword is not None and keyword.type == "interface":
        return "interface"
    modifiers = next((c for c in node.children if c.type == "modifiers"), None)
    if modifiers is not None:
        for m in modifiers.children:
            if m.type == "class_modifier" and m.text.decode("utf-8") == "enum":
                return "enum"
    return "class"


def _container_signature(node, kind: str, name: str) -> str:
    if node.type == "object_declaration":
        prefix = "object"
    elif kind == "interface":
        prefix = "interface"
    elif kind == "enum":
        prefix = "enum class"
    else:
        _class_decorators = ("data", "sealed", "annotation", "abstract", "open")
        modifier_words = _modifier_words(node)
        decorators = [w for w in modifier_words if w in _class_decorators]
        prefix = (" ".join(decorators) + " class").strip() if decorators else "class"

    parts = [f"{prefix} {name}"]

    pc = next((c for c in node.children if c.type == "primary_constructor"), None)
    if pc is not None:
        params = next((c for c in pc.children if c.type == "class_parameters"), None)
        if params is not None:
            parts[-1] = parts[-1] + params.text.decode("utf-8")

    delegation = next(
        (c for c in node.children if c.type == "delegation_specifiers"), None
    )
    if delegation is not None:
        bases = delegation.text.decode("utf-8")
        parts.append(f": {bases}")

    return " ".join(parts)


def _modifier_words(node) -> list[str]:
    modifiers = next((c for c in node.children if c.type == "modifiers"), None)
    if modifiers is None:
        return []
    out = []
    for m in modifiers.children:
        if m.type in (
            "class_modifier",
            "function_modifier",
            "property_modifier",
            "visibility_modifier",
            "inheritance_modifier",
            "member_modifier",
            "parameter_modifier",
        ):
            out.append(m.text.decode("utf-8"))
    return out


def _function_signature(node, name: str) -> str:
    # Children appear in source order. An extension function has a
    # `user_type` child positioned before `name`.
    receiver_text = ""
    params_text = "()"
    return_text = ""
    seen_name = False
    seen_params = False
    children = list(node.children)
    for i, c in enumerate(children):
        if c.type == "identifier" and not seen_name:
            seen_name = True
            continue
        if not seen_name and c.type == "user_type":
            receiver_text = c.text.decode("utf-8")
            continue
        if c.type == "function_value_parameters":
            params_text = c.text.decode("utf-8")
            seen_params = True
            continue
        if seen_params and c.type == "user_type":
            return_text = f": {c.text.decode('utf-8')}"
            break
    head = f"fun {receiver_text}.{name}" if receiver_text else f"fun {name}"
    return f"{head}{params_text}{return_text}"


def _property_kind(node) -> str:
    if "const" in _modifier_words(node):
        return "constant"
    return "property"


def _property_name(node) -> str | None:
    var = next((c for c in node.children if c.type == "variable_declaration"), None)
    if var is None:
        return None
    ident = next((c for c in var.children if c.type == "identifier"), None)
    if ident is None:
        return None
    return ident.text.decode("utf-8")


def _property_signature(node, name: str) -> str:
    keyword = next((c for c in node.children if c.type in ("val", "var")), None)
    kw = keyword.text.decode("utf-8") if keyword is not None else "val"
    _prop_prefix_words = (
        "const",
        "lateinit",
        "private",
        "public",
        "internal",
        "protected",
    )
    prefix_words = [w for w in _modifier_words(node) if w in _prop_prefix_words]
    prefix = (" ".join(prefix_words) + " ") if prefix_words else ""
    var = next((c for c in node.children if c.type == "variable_declaration"), None)
    type_text = ""
    if var is not None:
        ut = next((c for c in var.children if c.type == "user_type"), None)
        if ut is not None:
            type_text = f": {ut.text.decode('utf-8')}"
    return f"{prefix}{kw} {name}{type_text}"


def _bodies(node) -> list:
    return [c for c in node.children if c.type in ("class_body", "enum_class_body")]


def _package_name(root) -> str | None:
    for child in root.named_children:
        if child.type != "package_header":
            continue
        for inner in child.named_children:
            if inner.type == "qualified_identifier":
                return inner.text.decode("utf-8")
            if inner.type == "identifier":
                return inner.text.decode("utf-8")
    return None


def _kdoc(node) -> str | None:
    parent = node.parent
    if parent is None:
        return None
    siblings = parent.children
    idx = next((i for i, c in enumerate(siblings) if c.id == node.id), None)
    if idx is None or idx == 0:
        return None
    # Skip backwards over whitespace/non-comment tokens to find the closest
    # immediately preceding block_comment. We only accept it if no other
    # named (declaration-like) node sits between it and this node.
    j = idx - 1
    while j >= 0 and siblings[j].type in ("{", "}", ";"):
        j -= 1
    if j < 0:
        return None
    prev = siblings[j]
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
