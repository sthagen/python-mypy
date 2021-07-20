"""Tokenizers for three string formatting methods"""

import re
from typing import List, Tuple

from mypyc.ir.ops import Value, Integer
from mypyc.ir.rtypes import c_pyssize_t_rprimitive
from mypyc.irbuild.builder import IRBuilder
from mypyc.primitives.str_ops import str_build_op

# printf-style String Formatting:
# https://docs.python.org/3/library/stdtypes.html#old-string-formatting
printf_style_pattern = re.compile(r"""
    (
    %                                # Start sign
    (?:\((?P<key>[^)]*)\))?          # Optional: Mapping key
    (?P<flag>[-+#0 ]+)?              # Optional: Conversion flags
    (?P<width>\d+|\*)?               # Optional: Minimum field width
    (?:\.(?P<precision>\d+|\*))?     # Optional: Precision
    [hlL]?                           # Optional: Length modifier, Ignored
    (?P<type>[diouxXeEfFgGcrsa])     # Conversion type
    | %%)
    """, re.VERBOSE)


def tokenizer_printf_style(format_str: str) -> Tuple[List[str], List[str]]:
    """Tokenize a printf-style format string using regex.

    Return:
        A list of string literals and a list of conversion operations
    """
    literals = []
    format_ops = []
    last_end = 0

    for m in re.finditer(printf_style_pattern, format_str):
        cur_start = m.start(1)
        format_tmp = m.group(1)
        literals.append(format_str[last_end:cur_start])
        format_ops.append(format_tmp)
        last_end = cur_start + len(format_tmp)

    literals.append(format_str[last_end:])

    return literals, format_ops


def join_formatted_strings(builder: IRBuilder, literals: List[str],
                           substitutions: List[Value], line: int) -> Value:
    """Merge the list of literals and the list of substitutions
    alternatively using 'str_build_op'.

    Args:
        builder: IRBuilder
        literals: The literal substrings of the original format string.
                  After splitting the original format string, the
                  length of literals should be exactly one more than
                  substitutions.
        substitutions: Result Python strings of each conversion
        line: line number
    """
    # The first parameter for str_build_op is the total size of
    # the following PyObject*
    result_list: List[Value] = [Integer(0, c_pyssize_t_rprimitive)]
    for a, b in zip(literals, substitutions):
        if a:
            result_list.append(builder.load_str(a))
        result_list.append(b)
    if literals[-1]:
        result_list.append(builder.load_str(literals[-1]))

    # Special case for empty string and literal string
    if len(result_list) == 1:
        return builder.load_str("")
    if not substitutions and len(result_list) == 2:
        return result_list[1]

    result_list[0] = Integer(len(result_list) - 1, c_pyssize_t_rprimitive)
    return builder.call_c(str_build_op, result_list, line)
