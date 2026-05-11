from dataclasses import dataclass, field


@dataclass
class LanguageDef:
    extensions: list[str]
    grammar: str  # importable package name, e.g. "tree_sitter_python"; "" if none
    scip_binary: str  # checked via shutil.which at runtime
    pack_name: str = field(
        default=""
    )  # name in tree-sitter-language-pack, if no standalone package


LANGUAGES: dict[str, LanguageDef] = {
    "python": LanguageDef(
        extensions=[".py"],
        grammar="tree_sitter_python",
        scip_binary="scip-python",
    ),
    "go": LanguageDef(
        extensions=[".go"],
        grammar="tree_sitter_go",
        scip_binary="scip-go",
    ),
    "java": LanguageDef(
        extensions=[".java"],
        grammar="tree_sitter_java",
        scip_binary="scip-java",
    ),
    "gleam": LanguageDef(
        extensions=[".gleam"],
        grammar="",
        scip_binary="",
        pack_name="gleam",
    ),
    "erlang": LanguageDef(
        extensions=[".erl", ".hrl"],
        grammar="",
        scip_binary="",
        pack_name="erlang",
    ),
    "kotlin": LanguageDef(
        extensions=[".kt", ".kts"],
        grammar="tree_sitter_kotlin",
        scip_binary="scip-kotlin",
    ),
}
