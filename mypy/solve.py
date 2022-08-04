"""Type inference constraint solving"""

from collections import defaultdict
from typing import Dict, List, Optional

from mypy.constraints import SUPERTYPE_OF, Constraint
from mypy.join import join_types
from mypy.meet import meet_types
from mypy.subtypes import is_subtype
from mypy.types import (
    AnyType,
    Type,
    TypeOfAny,
    TypeVarId,
    UninhabitedType,
    UnionType,
    get_proper_type,
)


def solve_constraints(
    vars: List[TypeVarId],
    constraints: List[Constraint],
    strict: bool = True,
    infer_unions: bool = False,
) -> List[Optional[Type]]:
    """Solve type constraints.

    Return the best type(s) for type variables; each type can be None if the value of the variable
    could not be solved.

    If a variable has no constraints, if strict=True then arbitrarily
    pick NoneType as the value of the type variable.  If strict=False,
    pick AnyType.
    """
    # Collect a list of constraints for each type variable.
    cmap: Dict[TypeVarId, List[Constraint]] = defaultdict(list)
    for con in constraints:
        cmap[con.type_var].append(con)

    res: List[Optional[Type]] = []

    # Solve each type variable separately.
    for tvar in vars:
        bottom: Optional[Type] = None
        top: Optional[Type] = None
        candidate: Optional[Type] = None

        # Process each constraint separately, and calculate the lower and upper
        # bounds based on constraints. Note that we assume that the constraint
        # targets do not have constraint references.
        for c in cmap.get(tvar, []):
            if c.op == SUPERTYPE_OF:
                if bottom is None:
                    bottom = c.target
                else:
                    if infer_unions:
                        # This deviates from the general mypy semantics because
                        # recursive types are union-heavy in 95% of cases.
                        bottom = UnionType.make_union([bottom, c.target])
                    else:
                        bottom = join_types(bottom, c.target)
            else:
                if top is None:
                    top = c.target
                else:
                    top = meet_types(top, c.target)

        top = get_proper_type(top)
        bottom = get_proper_type(bottom)
        if isinstance(top, AnyType) or isinstance(bottom, AnyType):
            source_any = top if isinstance(top, AnyType) else bottom
            assert isinstance(source_any, AnyType)
            res.append(AnyType(TypeOfAny.from_another_any, source_any=source_any))
            continue
        elif bottom is None:
            if top:
                candidate = top
            else:
                # No constraints for type variable -- 'UninhabitedType' is the most specific type.
                if strict:
                    candidate = UninhabitedType()
                    candidate.ambiguous = True
                else:
                    candidate = AnyType(TypeOfAny.special_form)
        elif top is None:
            candidate = bottom
        elif is_subtype(bottom, top):
            candidate = bottom
        else:
            candidate = None
        res.append(candidate)

    return res
