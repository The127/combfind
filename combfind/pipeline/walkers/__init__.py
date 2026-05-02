from typing import Protocol

from combfind.pipeline.walkers.go import GoWalker
from combfind.pipeline.walkers.java import JavaWalker
from combfind.pipeline.walkers.python import PythonWalker


class Walker(Protocol):
    def extract_symbols(self, root, module_name: str) -> list[dict]: ...

    def extract_skeleton(self, source: str, kind: str) -> str: ...


_REGISTRY: dict[str, Walker] = {
    "python": PythonWalker(),
    "go": GoWalker(),
    "java": JavaWalker(),
}


def get_walker(lang: str) -> Walker:
    try:
        return _REGISTRY[lang]
    except KeyError:
        raise ValueError(f"no walker registered for language {lang!r}")
