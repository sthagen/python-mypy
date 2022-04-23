from typing import Sequence

cmp_op: Sequence[str]
hasconst: list[int]
hasname: list[int]
hasjrel: list[int]
hasjabs: list[int]
haslocal: list[int]
hascompare: list[int]
hasfree: list[int]
opname: list[str]

opmap: dict[str, int]
HAVE_ARGUMENT: int
EXTENDED_ARG: int
