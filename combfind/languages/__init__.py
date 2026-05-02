from dataclasses import dataclass


@dataclass
class LanguageDef:
    extensions: list[str]
    grammar: str  # importable package name, e.g. "tree_sitter_python"
    scip_binary: str  # checked via shutil.which at runtime


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
}
