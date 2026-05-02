; NOTE: used as documentation only — parse.py walks the AST directly via GleamWalker.

; Function declarations
(function
  name: (identifier) @function.name
  parameters: (function_parameters) @function.params
) @function.def

; Custom type definitions
(type_definition
  name: (type_name) @type.name
) @type.def

; Type aliases
(type_alias
  name: (type_name) @type.name
) @type.alias

; Module-level constants
(constant
  name: (identifier) @constant.name
) @constant.def
