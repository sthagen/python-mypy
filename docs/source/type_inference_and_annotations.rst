Type inference and type annotations
===================================

Type inference
**************

Mypy considers the initial assignment as the definition of a variable.
If you do not explicitly
specify the type of the variable, mypy infers the type based on the
static type of the value expression:

.. code-block:: python

   i = 1           # Infer type "int" for i
   l = [1, 2]      # Infer type "list[int]" for l

Type inference is not used in dynamically typed functions (those
without a function type annotation) — every local variable type defaults
to ``Any`` in such functions. ``Any`` is discussed later in more detail.

.. _explicit-var-types:

Explicit types for variables
****************************

You can override the inferred type of a variable by using a
variable type annotation:

.. code-block:: python

   from typing import Union

   x: Union[int, str] = 1

Without the type annotation, the type of ``x`` would be just ``int``. We
use an annotation to give it a more general type ``Union[int, str]`` (this
type means that the value can be either an ``int`` or a ``str``).
Mypy checks that the type of the initializer is compatible with the
declared type. The following example is not valid, since the initializer is
a floating point number, and this is incompatible with the declared
type:

.. code-block:: python

   x: Union[int, str] = 1.1  # Error!

.. note::

   The best way to think about this is that the type annotation sets the
   type of the variable, not the type of the expression. To force the
   type of an expression you can use :py:func:`cast(\<type\>, \<expression\>) <typing.cast>`.

Explicit types for collections
******************************

The type checker cannot always infer the type of a list or a
dictionary. This often arises when creating an empty list or
dictionary and assigning it to a new variable that doesn't have an explicit
variable type. Here is an example where mypy can't infer the type
without some help:

.. code-block:: python

   l = []  # Error: Need type annotation for "l"

In these cases you can give the type explicitly using a type annotation:

.. code-block:: python

   l: list[int] = []       # Create empty list with type list[int]
   d: dict[str, int] = {}  # Create empty dictionary (str -> int)

Similarly, you can also give an explicit type when creating an empty set:

.. code-block:: python

   s: set[int] = set()

.. note::

   Using type arguments (e.g. ``list[int]``) on builtin collections like
   :py:class:`list`,  :py:class:`dict`, :py:class:`tuple`, and  :py:class:`set`
   only works in Python 3.9 and later. For Python 3.8 and earlier, you must use
   :py:class:`~typing.List` (e.g. ``List[int]``), :py:class:`~typing.Dict`, and
   so on.


Compatibility of container types
********************************

The following program generates a mypy error, since ``list[int]``
is not compatible with ``list[object]``:

.. code-block:: python

   def f(l: list[object], k: list[int]) -> None:
       l = k  # Type check error: incompatible types in assignment

The reason why the above assignment is disallowed is that allowing the
assignment could result in non-int values stored in a list of ``int``:

.. code-block:: python

   def f(l: list[object], k: list[int]) -> None:
       l = k
       l.append('x')
       print(k[-1])  # Ouch; a string in list[int]

Other container types like :py:class:`dict` and :py:class:`set` behave similarly. We
will discuss how you can work around this in :ref:`variance`.

You can still run the above program; it prints ``x``. This illustrates
the fact that static types are used during type checking, but they do
not affect the runtime behavior of programs. You can run programs with
type check failures, which is often very handy when performing a large
refactoring. Thus you can always 'work around' the type system, and it
doesn't really limit what you can do in your program.

Context in type inference
*************************

Type inference is *bidirectional* and takes context into account. For
example, the following is valid:

.. code-block:: python

   def f(l: list[object]) -> None:
       l = [1, 2]  # Infer type list[object] for [1, 2], not list[int]

In an assignment, the type context is determined by the assignment
target. In this case this is ``l``, which has the type
``list[object]``. The value expression ``[1, 2]`` is type checked in
this context and given the type ``list[object]``. In the previous
example we introduced a new variable ``l``, and here the type context
was empty.

Declared argument types are also used for type context. In this program
mypy knows that the empty list ``[]`` should have type ``list[int]`` based
on the declared type of ``arg`` in ``foo``:

.. code-block:: python

    def foo(arg: list[int]) -> None:
        print('Items:', ''.join(str(a) for a in arg))

    foo([])  # OK

However, context only works within a single statement. Here mypy requires
an annotation for the empty list, since the context would only be available
in the following statement:

.. code-block:: python

    def foo(arg: list[int]) -> None:
        print('Items:', ', '.join(arg))

    a = []  # Error: Need type annotation for "a"
    foo(a)

Working around the issue is easy by adding a type annotation:

.. code-block:: Python

    ...
    a: list[int] = []  # OK
    foo(a)

Starred expressions
*******************

In most cases, mypy can infer the type of starred expressions from the
right-hand side of an assignment, but not always:

.. code-block:: python

    a, *bs = 1, 2, 3   # OK
    p, q, *rs = 1, 2   # Error: Type of rs cannot be inferred

On first line, the type of ``bs`` is inferred to be
``list[int]``. However, on the second line, mypy cannot infer the type
of ``rs``, because there is no right-hand side value for ``rs`` to
infer the type from. In cases like these, the starred expression needs
to be annotated with a starred type:

.. code-block:: python

    p, q, *rs = 1, 2  # type: int, int, list[int]

Here, the type of ``rs`` is set to ``list[int]``.

Silencing type errors
*********************

You might want to disable type checking on specific lines, or within specific
files in your codebase. To do that, you can use a ``# type: ignore`` comment.

For example, say that the web framework that you use now takes an integer
argument to ``run()``, which starts it on localhost on that port. Like so:

.. code-block:: python

    # Starting app on http://localhost:8000
    app.run(8000)

However, the type stubs that the package uses is not up-to-date, and it still
expects only ``str`` types for ``run()``. This would give you the following error:

.. code-block:: text

    error: Argument 1 to "run" of "A" has incompatible type "int"; expected "str"

If you cannot directly fix the type stubs yourself, you can temporarily
disable type checking on that line, by adding a ``# type: ignore``:

.. code-block:: python

    # Starting app on http://localhost:8000
    app.run(8000)  # type: ignore

This will suppress any mypy errors that would have raised on that specific line.

You should probably add some more information on the ``# type: ignore`` comment,
to explain why the ignore was added in the first place. This could be a link to
an issue on the repository responsible for the type stubs, or it could be a
short explanation of the bug. To do that, use this format:

.. code-block:: python

    # Starting app on http://localhost:8000
    app.run(8000)  # type: ignore  # `run()` now accepts an `int`, as a port


Mypy displays an error code for each error if you use
:option:`--show-error-codes <mypy --show-error-codes>`:

.. code-block:: text

   error: "str" has no attribute "trim"  [attr-defined]


It is possible to add a specific error-code in your ignore comment (e.g.
``# type: ignore[attr-defined]``) to clarify what's being silenced. You can
find more information about error codes :ref:`here <silence-error-codes>`.

Similarly, you can also ignore all mypy checks in a file, by adding a
``# type: ignore`` at the top of the file:

.. code-block:: python

    # type: ignore
    # This is a test file, skipping type checking in it.
    import unittest
    ...

Finally, adding a ``@typing.no_type_check`` decorator to a class, method or
function has the effect of ignoring that class, method or function.

.. code-block:: python

    @typing.no_type_check
    def foo() -> str:
       return 12345  # No error!
