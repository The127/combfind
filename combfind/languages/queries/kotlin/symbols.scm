; NOTE: used as documentation only — parse.py walks the AST directly via KotlinWalker.

; Top-level functions, methods, extension functions
(function_declaration
  name: (identifier) @function.name
) @function.def

; class / interface / enum class / data class / sealed class / annotation class
(class_declaration
  name: (identifier) @type.name
) @type.def

; Singletons and nested objects
(object_declaration
  name: (identifier) @object.name
) @object.def

; Companion objects (implicit name "Companion" if no identifier)
(companion_object) @companion.def

; Top-level and member val/var (incl. `const val`)
(property_declaration
  (variable_declaration (identifier) @property.name)
) @property.def

; Enum entries
(enum_entry
  (identifier) @enum_constant.name
) @enum_constant.def
