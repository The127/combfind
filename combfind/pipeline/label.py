def run(db_path: str, *, llm_model: str | None = None, llm_ctx: int | None = None, **_) -> None:
    if llm_model is None:
        raise ValueError("--llm-model is required for the label stage")
    raise NotImplementedError
