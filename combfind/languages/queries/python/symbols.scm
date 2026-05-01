; NOTE: these queries document intended captures but are not executed via tree-sitter
; Query API (removed in 0.24+). parse.py walks the AST directly using named_children.

; Function and method definitions
(function_definition
  name: (identifier) @function.name
  parameters: (parameters) @function.params
) @function.def

; Class definitions
(class_definition
  name: (identifier) @class.name
  superclasses: (argument_list)? @class.bases
) @class.def
