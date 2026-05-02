; NOTE: used as documentation only — parse.py walks the AST directly via ErlangWalker.

; Function declarations (multiple clauses appear as separate fun_decl nodes)
(fun_decl
  (function_clause
    name: (atom) @function.name
    (expr_args) @function.params
  )
) @function.def

; Type definitions
(type_alias
  (type_name
    (atom) @type.name
  )
) @type.def

; Record declarations
(record_decl
  (atom) @record.name
) @record.def
