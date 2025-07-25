"""Mechanisms for inferring function types based on callsites.

Currently works by collecting all argument types at callsites,
synthesizing a list of possible function types from that, trying them
all, and picking the one with the fewest errors that we think is the
"best".

Can return JSON that pyannotate can use to apply the annotations to code.

There are a bunch of TODOs here:
 * Maybe want a way to surface the choices not selected??
 * We can generate an exponential number of type suggestions, and probably want
   a way to not always need to check them all.
 * Our heuristics for what types to try are primitive and not yet
   supported by real practice.
 * More!

Other things:
 * This is super brute force. Could we integrate with the typechecker
   more to understand more about what is going on?
 * Like something with tracking constraints/unification variables?
 * No understanding of type variables at *all*
"""

from __future__ import annotations

import itertools
import json
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Callable, NamedTuple, TypedDict, TypeVar, cast

from mypy.argmap import map_actuals_to_formals
from mypy.build import Graph, State
from mypy.checkexpr import has_any_type
from mypy.find_sources import InvalidSourceList, SourceFinder
from mypy.join import join_type_list
from mypy.meet import meet_type_list
from mypy.modulefinder import PYTHON_EXTENSIONS
from mypy.nodes import (
    ARG_STAR,
    ARG_STAR2,
    ArgKind,
    CallExpr,
    Decorator,
    Expression,
    FuncDef,
    MypyFile,
    RefExpr,
    ReturnStmt,
    SymbolNode,
    SymbolTable,
    TypeInfo,
    Var,
)
from mypy.options import Options
from mypy.plugin import FunctionContext, MethodContext, Plugin
from mypy.server.update import FineGrainedBuildManager
from mypy.state import state
from mypy.traverser import TraverserVisitor
from mypy.typeops import bind_self, make_simplified_union
from mypy.types import (
    AnyType,
    CallableType,
    FunctionLike,
    Instance,
    NoneType,
    ProperType,
    TupleType,
    Type,
    TypeAliasType,
    TypedDictType,
    TypeOfAny,
    TypeStrVisitor,
    TypeTranslator,
    TypeVarType,
    UninhabitedType,
    UnionType,
    get_proper_type,
)
from mypy.types_utils import is_overlapping_none, remove_optional
from mypy.util import split_target


class PyAnnotateSignature(TypedDict):
    return_type: str
    arg_types: list[str]


class Callsite(NamedTuple):
    path: str
    line: int
    arg_kinds: list[list[ArgKind]]
    callee_arg_names: list[str | None]
    arg_names: list[list[str | None]]
    arg_types: list[list[Type]]


class SuggestionPlugin(Plugin):
    """Plugin that records all calls to a given target."""

    def __init__(self, target: str) -> None:
        if target.endswith((".__new__", ".__init__")):
            target = target.rsplit(".", 1)[0]

        self.target = target
        # List of call sites found by dmypy suggest:
        # (path, line, <arg kinds>, <arg names>, <arg types>)
        self.mystery_hits: list[Callsite] = []

    def get_function_hook(self, fullname: str) -> Callable[[FunctionContext], Type] | None:
        if fullname == self.target:
            return self.log
        else:
            return None

    def get_method_hook(self, fullname: str) -> Callable[[MethodContext], Type] | None:
        if fullname == self.target:
            return self.log
        else:
            return None

    def log(self, ctx: FunctionContext | MethodContext) -> Type:
        self.mystery_hits.append(
            Callsite(
                ctx.api.path,
                ctx.context.line,
                ctx.arg_kinds,
                ctx.callee_arg_names,
                ctx.arg_names,
                ctx.arg_types,
            )
        )
        return ctx.default_return_type


# NOTE: We could make this a bunch faster by implementing a StatementVisitor that skips
# traversing into expressions
class ReturnFinder(TraverserVisitor):
    """Visitor for finding all types returned from a function."""

    def __init__(self, typemap: dict[Expression, Type]) -> None:
        self.typemap = typemap
        self.return_types: list[Type] = []

    def visit_return_stmt(self, o: ReturnStmt) -> None:
        if o.expr is not None and o.expr in self.typemap:
            self.return_types.append(self.typemap[o.expr])

    def visit_func_def(self, o: FuncDef) -> None:
        # Skip nested functions
        pass


def get_return_types(typemap: dict[Expression, Type], func: FuncDef) -> list[Type]:
    """Find all the types returned by return statements in func."""
    finder = ReturnFinder(typemap)
    func.body.accept(finder)
    return finder.return_types


class ArgUseFinder(TraverserVisitor):
    """Visitor for finding all the types of arguments that each arg is passed to.

    This is extremely simple minded but might be effective anyways.
    """

    def __init__(self, func: FuncDef, typemap: dict[Expression, Type]) -> None:
        self.typemap = typemap
        self.arg_types: dict[SymbolNode, list[Type]] = {arg.variable: [] for arg in func.arguments}

    def visit_call_expr(self, o: CallExpr) -> None:
        if not any(isinstance(e, RefExpr) and e.node in self.arg_types for e in o.args):
            return

        typ = get_proper_type(self.typemap.get(o.callee))
        if not isinstance(typ, CallableType):
            return

        formal_to_actual = map_actuals_to_formals(
            o.arg_kinds,
            o.arg_names,
            typ.arg_kinds,
            typ.arg_names,
            lambda n: AnyType(TypeOfAny.special_form),
        )

        for i, args in enumerate(formal_to_actual):
            for arg_idx in args:
                arg = o.args[arg_idx]
                if isinstance(arg, RefExpr) and arg.node in self.arg_types:
                    self.arg_types[arg.node].append(typ.arg_types[i])


def get_arg_uses(typemap: dict[Expression, Type], func: FuncDef) -> list[list[Type]]:
    """Find all the types of arguments that each arg is passed to.

    For example, given
      def foo(x: int) -> None: ...
      def bar(x: str) -> None: ...
      def test(x, y):
          foo(x)
          bar(y)

    this will return [[int], [str]].
    """
    finder = ArgUseFinder(func, typemap)
    func.body.accept(finder)
    return [finder.arg_types[arg.variable] for arg in func.arguments]


class SuggestionFailure(Exception):
    pass


def is_explicit_any(typ: AnyType) -> bool:
    # Originally I wanted to count as explicit anything derived from an explicit any, but that
    # seemed too strict in some testing.
    # return (typ.type_of_any == TypeOfAny.explicit
    #         or (typ.source_any is not None and typ.source_any.type_of_any == TypeOfAny.explicit))
    # Important question: what should we do with source_any stuff? Does that count?
    # And actually should explicit anys count at all?? Maybe not!
    return typ.type_of_any == TypeOfAny.explicit


def is_implicit_any(typ: Type) -> bool:
    typ = get_proper_type(typ)
    return isinstance(typ, AnyType) and not is_explicit_any(typ)


def _arg_accepts_function(typ: ProperType) -> bool:
    return (
        # TypeVar / Callable
        isinstance(typ, (TypeVarType, CallableType))
        or
        # Protocol with __call__
        isinstance(typ, Instance)
        and typ.type.is_protocol
        and typ.type.get_method("__call__") is not None
    )


class SuggestionEngine:
    """Engine for finding call sites and suggesting signatures."""

    def __init__(
        self,
        fgmanager: FineGrainedBuildManager,
        *,
        json: bool,
        no_errors: bool = False,
        no_any: bool = False,
        flex_any: float | None = None,
        use_fixme: str | None = None,
        max_guesses: int | None = None,
    ) -> None:
        self.fgmanager = fgmanager
        self.manager = fgmanager.manager
        self.plugin = self.manager.plugin
        self.graph = fgmanager.graph
        self.finder = SourceFinder(self.manager.fscache, self.manager.options)

        self.give_json = json
        self.no_errors = no_errors
        self.flex_any = flex_any
        if no_any:
            self.flex_any = 1.0

        self.max_guesses = max_guesses or 64
        self.use_fixme = use_fixme

    def suggest(self, function: str) -> str:
        """Suggest an inferred type for function."""
        mod, func_name, node = self.find_node(function)

        with self.restore_after(mod):
            with self.with_export_types():
                suggestion = self.get_suggestion(mod, node)

        if self.give_json:
            return self.json_suggestion(mod, func_name, node, suggestion)
        else:
            return self.format_signature(suggestion)

    def suggest_callsites(self, function: str) -> str:
        """Find a list of call sites of function."""
        mod, _, node = self.find_node(function)
        with self.restore_after(mod):
            callsites, _ = self.get_callsites(node)

        return "\n".join(
            dedup(
                [
                    f"{path}:{line}: {self.format_args(arg_kinds, arg_names, arg_types)}"
                    for path, line, arg_kinds, _, arg_names, arg_types in callsites
                ]
            )
        )

    @contextmanager
    def restore_after(self, module: str) -> Iterator[None]:
        """Context manager that reloads a module after executing the body.

        This should undo any damage done to the module state while mucking around.
        """
        try:
            yield
        finally:
            self.reload(self.graph[module])

    @contextmanager
    def with_export_types(self) -> Iterator[None]:
        """Context manager that enables the export_types flag in the body.

        This causes type information to be exported into the manager's all_types variable.
        """
        old = self.manager.options.export_types
        self.manager.options.export_types = True
        try:
            yield
        finally:
            self.manager.options.export_types = old

    def get_trivial_type(self, fdef: FuncDef) -> CallableType:
        """Generate a trivial callable type from a func def, with all Anys"""
        # The Anys are marked as being from the suggestion engine
        # since they need some special treatment (specifically,
        # constraint generation ignores them.)
        return CallableType(
            [AnyType(TypeOfAny.suggestion_engine) for _ in fdef.arg_kinds],
            fdef.arg_kinds,
            fdef.arg_names,
            AnyType(TypeOfAny.suggestion_engine),
            self.named_type("builtins.function"),
        )

    def get_starting_type(self, fdef: FuncDef) -> CallableType:
        if isinstance(fdef.type, CallableType):
            return make_suggestion_anys(fdef.type)
        else:
            return self.get_trivial_type(fdef)

    def get_args(
        self,
        is_method: bool,
        base: CallableType,
        defaults: list[Type | None],
        callsites: list[Callsite],
        uses: list[list[Type]],
    ) -> list[list[Type]]:
        """Produce a list of type suggestions for each argument type."""
        types: list[list[Type]] = []
        for i in range(len(base.arg_kinds)):
            # Make self args Any but this will get overridden somewhere in the checker
            if i == 0 and is_method:
                types.append([AnyType(TypeOfAny.suggestion_engine)])
                continue

            all_arg_types = []
            for call in callsites:
                for typ in call.arg_types[i - is_method]:
                    # Collect all the types except for implicit anys
                    if not is_implicit_any(typ):
                        all_arg_types.append(typ)
            all_use_types = []
            for typ in uses[i]:
                # Collect all the types except for implicit anys
                if not is_implicit_any(typ):
                    all_use_types.append(typ)
            # Add in any default argument types
            default = defaults[i]
            if default:
                all_arg_types.append(default)
                if all_use_types:
                    all_use_types.append(default)

            arg_types = []

            if all_arg_types and all(
                isinstance(get_proper_type(tp), NoneType) for tp in all_arg_types
            ):
                arg_types.append(
                    UnionType.make_union([all_arg_types[0], AnyType(TypeOfAny.explicit)])
                )
            elif all_arg_types:
                arg_types.extend(generate_type_combinations(all_arg_types))
            else:
                arg_types.append(AnyType(TypeOfAny.explicit))

            if all_use_types:
                # This is a meet because the type needs to be compatible with all the uses
                arg_types.append(meet_type_list(all_use_types))

            types.append(arg_types)
        return types

    def get_default_arg_types(self, fdef: FuncDef) -> list[Type | None]:
        return [
            self.manager.all_types[arg.initializer] if arg.initializer else None
            for arg in fdef.arguments
        ]

    def get_guesses(
        self,
        is_method: bool,
        base: CallableType,
        defaults: list[Type | None],
        callsites: list[Callsite],
        uses: list[list[Type]],
    ) -> list[CallableType]:
        """Compute a list of guesses for a function's type.

        This focuses just on the argument types, and doesn't change the provided return type.
        """
        options = self.get_args(is_method, base, defaults, callsites, uses)

        # Take the first `max_guesses` guesses.
        product = itertools.islice(itertools.product(*options), 0, self.max_guesses)
        return [refine_callable(base, base.copy_modified(arg_types=list(x))) for x in product]

    def get_callsites(self, func: FuncDef) -> tuple[list[Callsite], list[str]]:
        """Find all call sites of a function."""
        new_type = self.get_starting_type(func)

        collector_plugin = SuggestionPlugin(func.fullname)

        self.plugin._plugins.insert(0, collector_plugin)
        try:
            errors = self.try_type(func, new_type)
        finally:
            self.plugin._plugins.pop(0)

        return collector_plugin.mystery_hits, errors

    def filter_options(
        self, guesses: list[CallableType], is_method: bool, ignore_return: bool
    ) -> list[CallableType]:
        """Apply any configured filters to the possible guesses.

        Currently the only option is filtering based on Any prevalance."""
        return [
            t
            for t in guesses
            if self.flex_any is None
            or any_score_callable(t, is_method, ignore_return) >= self.flex_any
        ]

    def find_best(self, func: FuncDef, guesses: list[CallableType]) -> tuple[CallableType, int]:
        """From a list of possible function types, find the best one.

        For best, we want the fewest errors, then the best "score" from score_callable.
        """
        if not guesses:
            raise SuggestionFailure("No guesses that match criteria!")
        errors = {guess: self.try_type(func, guess) for guess in guesses}
        best = min(guesses, key=lambda s: (count_errors(errors[s]), self.score_callable(s)))
        return best, count_errors(errors[best])

    def get_guesses_from_parent(self, node: FuncDef) -> list[CallableType]:
        """Try to get a guess of a method type from a parent class."""
        if not node.info:
            return []

        for parent in node.info.mro[1:]:
            pnode = parent.names.get(node.name)
            if pnode and isinstance(pnode.node, (FuncDef, Decorator)):
                typ = get_proper_type(pnode.node.type)
                # FIXME: Doesn't work right with generic types
                if isinstance(typ, CallableType) and len(typ.arg_types) == len(node.arguments):
                    # Return the first thing we find, since it probably doesn't make sense
                    # to grab things further up in the chain if an earlier parent has it.
                    return [typ]

        return []

    def get_suggestion(self, mod: str, node: FuncDef) -> PyAnnotateSignature:
        """Compute a suggestion for a function.

        Return the type and whether the first argument should be ignored.
        """
        graph = self.graph
        callsites, orig_errors = self.get_callsites(node)
        uses = get_arg_uses(self.manager.all_types, node)

        if self.no_errors and orig_errors:
            raise SuggestionFailure("Function does not typecheck.")

        is_method = bool(node.info) and node.has_self_or_cls_argument

        with state.strict_optional_set(graph[mod].options.strict_optional):
            guesses = self.get_guesses(
                is_method,
                self.get_starting_type(node),
                self.get_default_arg_types(node),
                callsites,
                uses,
            )
        guesses += self.get_guesses_from_parent(node)
        guesses = self.filter_options(guesses, is_method, ignore_return=True)
        best, _ = self.find_best(node, guesses)

        # Now try to find the return type!
        self.try_type(node, best)
        returns = get_return_types(self.manager.all_types, node)
        with state.strict_optional_set(graph[mod].options.strict_optional):
            if returns:
                ret_types = generate_type_combinations(returns)
            else:
                ret_types = [NoneType()]

        guesses = [best.copy_modified(ret_type=refine_type(best.ret_type, t)) for t in ret_types]
        guesses = self.filter_options(guesses, is_method, ignore_return=False)
        best, errors = self.find_best(node, guesses)

        if self.no_errors and errors:
            raise SuggestionFailure("No annotation without errors")

        return self.pyannotate_signature(mod, is_method, best)

    def format_args(
        self,
        arg_kinds: list[list[ArgKind]],
        arg_names: list[list[str | None]],
        arg_types: list[list[Type]],
    ) -> str:
        args: list[str] = []
        for i in range(len(arg_types)):
            for kind, name, typ in zip(arg_kinds[i], arg_names[i], arg_types[i]):
                arg = self.format_type(None, typ)
                if kind == ARG_STAR:
                    arg = "*" + arg
                elif kind == ARG_STAR2:
                    arg = "**" + arg
                elif kind.is_named():
                    if name:
                        arg = f"{name}={arg}"
            args.append(arg)
        return f"({', '.join(args)})"

    def find_node(self, key: str) -> tuple[str, str, FuncDef]:
        """From a target name, return module/target names and the func def.

        The 'key' argument can be in one of two formats:
        * As the function full name, e.g., package.module.Cls.method
        * As the function location as file and line separated by column,
          e.g., path/to/file.py:42
        """
        # TODO: Also return OverloadedFuncDef -- currently these are ignored.
        node: SymbolNode | None = None
        if ":" in key:
            # A colon might be part of a drive name on Windows (like `C:/foo/bar`)
            # and is also used as a delimiter between file path and lineno.
            # If a colon is there for any of those reasons, it must be a file+line
            # reference.
            platform_key_count = 2 if sys.platform == "win32" else 1
            if key.count(":") > platform_key_count:
                raise SuggestionFailure(
                    "Malformed location for function: {}. Must be either"
                    " package.module.Class.method or path/to/file.py:line".format(key)
                )
            file, line = key.rsplit(":", 1)
            if not line.isdigit():
                raise SuggestionFailure(f"Line number must be a number. Got {line}")
            line_number = int(line)
            modname, node = self.find_node_by_file_and_line(file, line_number)
            tail = node.fullname[len(modname) + 1 :]  # add one to account for '.'
        else:
            target = split_target(self.fgmanager.graph, key)
            if not target:
                raise SuggestionFailure(f"Cannot find module for {key}")
            modname, tail = target
            node = self.find_node_by_module_and_name(modname, tail)

        if isinstance(node, Decorator):
            node = self.extract_from_decorator(node)
            if not node:
                raise SuggestionFailure(f"Object {key} is a decorator we can't handle")

        if not isinstance(node, FuncDef):
            raise SuggestionFailure(f"Object {key} is not a function")

        return modname, tail, node

    def find_node_by_module_and_name(self, modname: str, tail: str) -> SymbolNode | None:
        """Find symbol node by module id and qualified name.

        Raise SuggestionFailure if can't find one.
        """
        tree = self.ensure_loaded(self.fgmanager.graph[modname])

        # N.B. This is reimplemented from update's lookup_target
        # basically just to produce better error messages.

        names: SymbolTable = tree.names

        # Look through any classes
        components = tail.split(".")
        for i, component in enumerate(components[:-1]):
            if component not in names:
                raise SuggestionFailure(
                    "Unknown class {}.{}".format(modname, ".".join(components[: i + 1]))
                )
            node: SymbolNode | None = names[component].node
            if not isinstance(node, TypeInfo):
                raise SuggestionFailure(
                    "Object {}.{} is not a class".format(modname, ".".join(components[: i + 1]))
                )
            names = node.names

        # Look for the actual function/method
        funcname = components[-1]
        if funcname not in names:
            key = modname + "." + tail
            raise SuggestionFailure(
                "Unknown {} {}".format("method" if len(components) > 1 else "function", key)
            )
        return names[funcname].node

    def find_node_by_file_and_line(self, file: str, line: int) -> tuple[str, SymbolNode]:
        """Find symbol node by path to file and line number.

        Find the first function declared *before or on* the line number.

        Return module id and the node found. Raise SuggestionFailure if can't find one.
        """
        if not any(file.endswith(ext) for ext in PYTHON_EXTENSIONS):
            raise SuggestionFailure("Source file is not a Python file")
        try:
            modname, _ = self.finder.crawl_up(os.path.normpath(file))
        except InvalidSourceList as e:
            raise SuggestionFailure("Invalid source file name: " + file) from e
        if modname not in self.graph:
            raise SuggestionFailure("Unknown module: " + modname)
        # We must be sure about any edits in this file as this might affect the line numbers.
        tree = self.ensure_loaded(self.fgmanager.graph[modname], force=True)
        node: SymbolNode | None = None
        closest_line: int | None = None
        # TODO: Handle nested functions.
        for _, sym, _ in tree.local_definitions():
            if isinstance(sym.node, (FuncDef, Decorator)):
                sym_line = sym.node.line
            # TODO: add support for OverloadedFuncDef.
            else:
                continue

            # We want the closest function above the specified line
            if sym_line <= line and (closest_line is None or sym_line > closest_line):
                closest_line = sym_line
                node = sym.node
        if not node:
            raise SuggestionFailure(f"Cannot find a function at line {line}")
        return modname, node

    def extract_from_decorator(self, node: Decorator) -> FuncDef | None:
        for dec in node.decorators:
            typ = None
            if isinstance(dec, RefExpr) and isinstance(dec.node, (Var, FuncDef)):
                typ = get_proper_type(dec.node.type)
            elif (
                isinstance(dec, CallExpr)
                and isinstance(dec.callee, RefExpr)
                and isinstance(dec.callee.node, (Decorator, FuncDef, Var))
                and isinstance((call_tp := get_proper_type(dec.callee.node.type)), CallableType)
            ):
                typ = get_proper_type(call_tp.ret_type)

            if isinstance(typ, Instance):
                call_method = typ.type.get_method("__call__")
                if isinstance(call_method, FuncDef) and isinstance(call_method.type, FunctionLike):
                    typ = bind_self(call_method.type, None)

            if not isinstance(typ, FunctionLike):
                return None
            for ct in typ.items:
                if not (
                    len(ct.arg_types) == 1
                    and _arg_accepts_function(get_proper_type(ct.arg_types[0]))
                    and ct.arg_types[0] == ct.ret_type
                ):
                    return None

        return node.func

    def try_type(self, func: FuncDef, typ: ProperType) -> list[str]:
        """Recheck a function while assuming it has type typ.

        Return all error messages.
        """
        old = func.unanalyzed_type
        # During reprocessing, unanalyzed_type gets copied to type (by aststrip).
        # We set type to None to ensure that the type always changes during
        # reprocessing.
        func.type = None
        func.unanalyzed_type = typ
        try:
            res = self.fgmanager.trigger(func.fullname)
            # if res:
            #     print('===', typ)
            #     print('\n'.join(res))
            return res
        finally:
            func.unanalyzed_type = old

    def reload(self, state: State) -> list[str]:
        """Recheck the module given by state."""
        assert state.path is not None
        self.fgmanager.flush_cache()
        return self.fgmanager.update([(state.id, state.path)], [])

    def ensure_loaded(self, state: State, force: bool = False) -> MypyFile:
        """Make sure that the module represented by state is fully loaded."""
        if not state.tree or state.tree.is_cache_skeleton or force:
            self.reload(state)
        assert state.tree is not None
        return state.tree

    def named_type(self, s: str) -> Instance:
        return self.manager.semantic_analyzer.named_type(s)

    def json_suggestion(
        self, mod: str, func_name: str, node: FuncDef, suggestion: PyAnnotateSignature
    ) -> str:
        """Produce a json blob for a suggestion suitable for application by pyannotate."""
        # pyannotate irritatingly drops class names for class and static methods
        if node.is_class or node.is_static:
            func_name = func_name.split(".", 1)[-1]

        # pyannotate works with either paths relative to where the
        # module is rooted or with absolute paths. We produce absolute
        # paths because it is simpler.
        path = os.path.abspath(self.graph[mod].xpath)

        obj = {
            "signature": suggestion,
            "line": node.line,
            "path": path,
            "func_name": func_name,
            "samples": 0,
        }
        return json.dumps([obj], sort_keys=True)

    def pyannotate_signature(
        self, cur_module: str | None, is_method: bool, typ: CallableType
    ) -> PyAnnotateSignature:
        """Format a callable type as a pyannotate dict"""
        start = int(is_method)
        return {
            "arg_types": [self.format_type(cur_module, t) for t in typ.arg_types[start:]],
            "return_type": self.format_type(cur_module, typ.ret_type),
        }

    def format_signature(self, sig: PyAnnotateSignature) -> str:
        """Format a callable type in a way suitable as an annotation... kind of"""
        return f"({', '.join(sig['arg_types'])}) -> {sig['return_type']}"

    def format_type(self, cur_module: str | None, typ: Type) -> str:
        if self.use_fixme and isinstance(get_proper_type(typ), AnyType):
            return self.use_fixme
        return typ.accept(TypeFormatter(cur_module, self.graph, self.manager.options))

    def score_type(self, t: Type, arg_pos: bool) -> int:
        """Generate a score for a type that we use to pick which type to use.

        Lower is better, prefer non-union/non-any types. Don't penalize optionals.
        """
        t = get_proper_type(t)
        if isinstance(t, AnyType):
            return 20
        if arg_pos and isinstance(t, NoneType):
            return 20
        if isinstance(t, UnionType):
            if any(isinstance(get_proper_type(x), AnyType) for x in t.items):
                return 20
            if any(has_any_type(x) for x in t.items):
                return 15
            if not is_overlapping_none(t):
                return 10
        if isinstance(t, CallableType) and (has_any_type(t) or is_tricky_callable(t)):
            return 10
        return 0

    def score_callable(self, t: CallableType) -> int:
        return sum(self.score_type(x, arg_pos=True) for x in t.arg_types) + self.score_type(
            t.ret_type, arg_pos=False
        )


def any_score_type(ut: Type, arg_pos: bool) -> float:
    """Generate a very made up number representing the Anyness of a type.

    Higher is better, 1.0 is max
    """
    t = get_proper_type(ut)
    if isinstance(t, AnyType) and t.type_of_any != TypeOfAny.suggestion_engine:
        return 0
    if isinstance(t, NoneType) and arg_pos:
        return 0.5
    if isinstance(t, UnionType):
        if any(isinstance(get_proper_type(x), AnyType) for x in t.items):
            return 0.5
        if any(has_any_type(x) for x in t.items):
            return 0.25
    if isinstance(t, CallableType) and is_tricky_callable(t):
        return 0.5
    if has_any_type(t):
        return 0.5

    return 1.0


def any_score_callable(t: CallableType, is_method: bool, ignore_return: bool) -> float:
    # Ignore the first argument of methods
    scores = [any_score_type(x, arg_pos=True) for x in t.arg_types[int(is_method) :]]
    # Return type counts twice (since it spreads type information), unless it is
    # None in which case it does not count at all. (Though it *does* still count
    # if there are no arguments.)
    if not isinstance(get_proper_type(t.ret_type), NoneType) or not scores:
        ret = 1.0 if ignore_return else any_score_type(t.ret_type, arg_pos=False)
        scores += [ret, ret]

    return sum(scores) / len(scores)


def is_tricky_callable(t: CallableType) -> bool:
    """Is t a callable that we need to put a ... in for syntax reasons?"""
    return t.is_ellipsis_args or any(k.is_star() or k.is_named() for k in t.arg_kinds)


class TypeFormatter(TypeStrVisitor):
    """Visitor used to format types"""

    # TODO: Probably a lot
    def __init__(self, module: str | None, graph: Graph, options: Options) -> None:
        super().__init__(options=options)
        self.module = module
        self.graph = graph

    def visit_any(self, t: AnyType) -> str:
        if t.missing_import_name:
            return t.missing_import_name
        else:
            return "Any"

    def visit_instance(self, t: Instance) -> str:
        s = t.type.fullname or t.type.name or None
        if s is None:
            return "<???>"

        mod_obj = split_target(self.graph, s)
        assert mod_obj
        mod, obj = mod_obj

        # If a class is imported into the current module, rewrite the reference
        # to point to the current module. This helps the annotation tool avoid
        # inserting redundant imports when a type has been reexported.
        if self.module:
            parts = obj.split(".")  # need to split the object part if it is a nested class
            tree = self.graph[self.module].tree
            if tree and parts[0] in tree.names and mod not in tree.names:
                mod = self.module

        if (mod, obj) == ("builtins", "tuple"):
            mod, obj = "typing", "Tuple[" + t.args[0].accept(self) + ", ...]"
        elif t.args:
            obj += f"[{self.list_str(t.args)}]"

        if mod_obj == ("builtins", "unicode"):
            return "Text"
        elif mod == "builtins":
            return obj
        else:
            delim = "." if "." not in obj else ":"
            return mod + delim + obj

    def visit_tuple_type(self, t: TupleType) -> str:
        if t.partial_fallback and t.partial_fallback.type:
            fallback_name = t.partial_fallback.type.fullname
            if fallback_name != "builtins.tuple":
                return t.partial_fallback.accept(self)
        s = self.list_str(t.items)
        return f"Tuple[{s}]"

    def visit_uninhabited_type(self, t: UninhabitedType) -> str:
        return "Any"

    def visit_typeddict_type(self, t: TypedDictType) -> str:
        return t.fallback.accept(self)

    def visit_union_type(self, t: UnionType) -> str:
        if len(t.items) == 2 and is_overlapping_none(t):
            return f"Optional[{remove_optional(t).accept(self)}]"
        else:
            return super().visit_union_type(t)

    def visit_callable_type(self, t: CallableType) -> str:
        # TODO: use extended callables?
        if is_tricky_callable(t):
            arg_str = "..."
        else:
            # Note: for default arguments, we just assume that they
            # are required.  This isn't right, but neither is the
            # other thing, and I suspect this will produce more better
            # results than falling back to `...`
            args = [typ.accept(self) for typ in t.arg_types]
            arg_str = f"[{', '.join(args)}]"

        return f"Callable[{arg_str}, {t.ret_type.accept(self)}]"


TType = TypeVar("TType", bound=Type)


def make_suggestion_anys(t: TType) -> TType:
    """Make all anys in the type as coming from the suggestion engine.

    This keeps those Anys from influencing constraint generation,
    which allows us to do better when refining types.
    """
    return cast(TType, t.accept(MakeSuggestionAny()))


class MakeSuggestionAny(TypeTranslator):
    def visit_any(self, t: AnyType) -> Type:
        if not t.missing_import_name:
            return t.copy_modified(type_of_any=TypeOfAny.suggestion_engine)
        else:
            return t

    def visit_type_alias_type(self, t: TypeAliasType) -> Type:
        return t.copy_modified(args=[a.accept(self) for a in t.args])


def generate_type_combinations(types: list[Type]) -> list[Type]:
    """Generate possible combinations of a list of types.

    mypy essentially supports two different ways to do this: joining the types
    and unioning the types. We try both.
    """
    joined_type = join_type_list(types)
    union_type = make_simplified_union(types)
    if joined_type == union_type:
        return [joined_type]
    else:
        return [joined_type, union_type]


def count_errors(msgs: list[str]) -> int:
    return len([x for x in msgs if " error: " in x])


def refine_type(ti: Type, si: Type) -> Type:
    """Refine `ti` by replacing Anys in it with information taken from `si`

    This basically works by, when the types have the same structure,
    traversing both of them in parallel and replacing Any on the left
    with whatever the type on the right is. If the types don't have the
    same structure (or aren't supported), the left type is chosen.

    For example:
      refine(Any, T) = T,  for all T
      refine(float, int) = float
      refine(List[Any], List[int]) = List[int]
      refine(Dict[int, Any], Dict[Any, int]) = Dict[int, int]
      refine(Tuple[int, Any], Tuple[Any, int]) = Tuple[int, int]

      refine(Callable[[Any], Any], Callable[[int], int]) = Callable[[int], int]
      refine(Callable[..., int], Callable[[int, float], Any]) = Callable[[int, float], int]

      refine(Optional[Any], int) = Optional[int]
      refine(Optional[Any], Optional[int]) = Optional[int]
      refine(Optional[Any], Union[int, str]) = Optional[Union[int, str]]
      refine(Optional[List[Any]], List[int]) = List[int]

    """
    t = get_proper_type(ti)
    s = get_proper_type(si)

    if isinstance(t, AnyType):
        # If s is also an Any, we return if it is a missing_import Any
        return t if isinstance(s, AnyType) and t.missing_import_name else s

    if isinstance(t, Instance) and isinstance(s, Instance) and t.type == s.type:
        return t.copy_modified(args=[refine_type(ta, sa) for ta, sa in zip(t.args, s.args)])

    if (
        isinstance(t, TupleType)
        and isinstance(s, TupleType)
        and t.partial_fallback == s.partial_fallback
        and len(t.items) == len(s.items)
    ):
        return t.copy_modified(items=[refine_type(ta, sa) for ta, sa in zip(t.items, s.items)])

    if isinstance(t, CallableType) and isinstance(s, CallableType):
        return refine_callable(t, s)

    if isinstance(t, UnionType):
        return refine_union(t, s)

    # TODO: Refining of builtins.tuple, Type?

    return t


def refine_union(t: UnionType, s: ProperType) -> Type:
    """Refine a union type based on another type.

    This is done by refining every component of the union against the
    right hand side type (or every component of its union if it is
    one). If an element of the union is successfully refined, we drop it
    from the union in favor of the refined versions.
    """
    # Don't try to do any union refining if the types are already the
    # same.  This prevents things like refining Optional[Any] against
    # itself and producing None.
    if t == s:
        return t

    rhs_items = s.items if isinstance(s, UnionType) else [s]

    new_items = []
    for lhs in t.items:
        refined = False
        for rhs in rhs_items:
            new = refine_type(lhs, rhs)
            if new != lhs:
                new_items.append(new)
                refined = True
        if not refined:
            new_items.append(lhs)

    # Turn strict optional on when simplifying the union since we
    # don't want to drop Nones.
    with state.strict_optional_set(True):
        return make_simplified_union(new_items)


def refine_callable(t: CallableType, s: CallableType) -> CallableType:
    """Refine a callable based on another.

    See comments for refine_type.
    """
    if t.fallback != s.fallback:
        return t

    if t.is_ellipsis_args and not is_tricky_callable(s):
        return s.copy_modified(ret_type=refine_type(t.ret_type, s.ret_type))

    if is_tricky_callable(t) or t.arg_kinds != s.arg_kinds:
        return t

    return t.copy_modified(
        arg_types=[refine_type(ta, sa) for ta, sa in zip(t.arg_types, s.arg_types)],
        ret_type=refine_type(t.ret_type, s.ret_type),
    )


T = TypeVar("T")


def dedup(old: list[T]) -> list[T]:
    new: list[T] = []
    for x in old:
        if x not in new:
            new.append(x)
    return new
