; NOTE: see symbols.scm — used by index.py as documentation; AST is walked directly.

; import module
(import_statement
  name: (dotted_name) @import.module
)

; from module import name
(import_from_statement
  module_name: (dotted_name)? @import.from_module
  name: [(dotted_name) (aliased_import)] @import.name
)

; function/method calls
(call
  function: [
    (identifier) @call.name
    (attribute
      object: (_) @call.object
      attribute: (identifier) @call.attr
    )
  ]
)
