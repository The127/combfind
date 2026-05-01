from dataclasses import dataclass


@dataclass
class LanguageDef:
    extensions: list[str]
    grammar: str       # importable package name, e.g. "tree_sitter_python"
    scip_binary: str   # checked via shutil.which at runtime


LANGUAGES: dict[str, LanguageDef] = {
    "python": LanguageDef(
        extensions=[".py"],
        grammar="tree_sitter_python",
        scip_binary="scip-python",
    ),
}
