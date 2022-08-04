.. _getting-started:

Getting started
===============

This chapter introduces some core concepts of mypy, including function
annotations, the :py:mod:`typing` module, stub files, and more.

Be sure to read this chapter carefully, as the rest of the documentation
may not make much sense otherwise.

Installing and running mypy
***************************

Mypy requires Python 3.6 or later to run.  Once you've
`installed Python 3 <https://www.python.org/downloads/>`_,
install mypy using pip:

.. code-block:: shell

    $ python3 -m pip install mypy

Once mypy is installed, run it by using the ``mypy`` tool:

.. code-block:: shell

    $ mypy program.py

This command makes mypy *type check* your ``program.py`` file and print
out any errors it finds. Mypy will type check your code *statically*: this
means that it will check for errors without ever running your code, just
like a linter.

This means that you are always free to ignore the errors mypy reports and
treat them as just warnings, if you so wish: mypy runs independently from
Python itself.

However, if you try directly running mypy on your existing Python code, it
will most likely report little to no errors: you must add *type annotations*
to your code to take full advantage of mypy. See the section below for details.

Function signatures and dynamic vs static typing
************************************************

A function without type annotations is considered to be *dynamically typed* by mypy:

.. code-block:: python

   def greeting(name):
       return 'Hello ' + name

By default, mypy will **not** type check dynamically typed functions. This means
that with a few exceptions, mypy will not report any errors with regular unannotated Python.

This is the case even if you misuse the function: for example, mypy would currently
not report any errors if you tried running ``greeting(3)`` or ``greeting(b"Alice")``
even though those function calls would result in errors at runtime.

You can teach mypy to detect these kinds of bugs by adding *type annotations* (also
known as *type hints*). For example, you can teach mypy that ``greeting`` both accepts
and returns a string like so:

.. code-block:: python

   def greeting(name: str) -> str:
       return 'Hello ' + name

This function is now *statically typed*: mypy can use the provided type hints to detect
incorrect usages of the ``greeting`` function. For example, it will reject the following
calls since the arguments have invalid types:

.. code-block:: python

   def greeting(name: str) -> str:
       return 'Hello ' + name

   greeting(3)         # Argument 1 to "greeting" has incompatible type "int"; expected "str"
   greeting(b'Alice')  # Argument 1 to "greeting" has incompatible type "bytes"; expected "str"

Note that this is all still valid Python 3 code! The function annotation syntax
shown above was added to Python :pep:`as a part of Python 3.0 <3107>`.

Being able to pick whether you want a function to be dynamically or statically
typed can be very helpful. For example, if you are migrating an existing
Python codebase to use static types, it's usually easier to migrate by incrementally
adding type hints to your code rather than adding them all at once. Similarly,
when you are prototyping a new feature, it may be convenient to initially implement
the code using dynamic typing and only add type hints later once the code is more stable.

Once you are finished migrating or prototyping your code, you can make mypy warn you
if you add a dynamic function by mistake by using the :option:`--disallow-untyped-defs <mypy --disallow-untyped-defs>`
flag. See :ref:`command-line` for more information on configuring mypy.

.. note::

   The earlier stages of analysis performed by mypy may report errors
   even for dynamically typed functions. However, you should not rely
   on this, as this may change in the future.

More function signatures
************************

Here are a few more examples of adding type hints to function signatures.

If a function does not explicitly return a value, give it a return
type of ``None``. Using a ``None`` result in a statically typed
context results in a type check error:

.. code-block:: python

   def p() -> None:
       print('hello')

   a = p()  # Error: "p" does not return a value

Make sure to remember to include ``None``: if you don't, the function
will be dynamically typed. For example:

.. code-block:: python

   def f():
       1 + 'x'  # No static type error (dynamically typed)

   def g() -> None:
       1 + 'x'  # Type check error (statically typed)

Arguments with default values can be annotated like so:

.. code-block:: python

   def greeting(name: str, excited: bool = False) -> str:
       message = f'Hello, {name}'
       if excited:
           message += '!!!'
       return message

``*args`` and ``**kwargs`` arguments can be annotated like so:

.. code-block:: python

   def stars(*args: int, **kwargs: float) -> None:
       # 'args' has type 'tuple[int, ...]' (a tuple of ints)
       # 'kwargs' has type 'dict[str, float]' (a dict of strs to floats)
       for arg in args:
           print(arg)
       for key, value in kwargs.items():
           print(key, value)

Additional types, and the typing module
***************************************

So far, we've added type hints that use only basic concrete types like
``str`` and ``float``. What if we want to express more complex types,
such as "a list of strings" or "an iterable of ints"?

For example, to indicate that some function can accept a list of
strings, use the ``list[str]`` type (Python 3.9 and later):

.. code-block:: python

   def greet_all(names: list[str]) -> None:
       for name in names:
           print('Hello ' + name)

   names = ["Alice", "Bob", "Charlie"]
   ages = [10, 20, 30]

   greet_all(names)   # Ok!
   greet_all(ages)    # Error due to incompatible types

The :py:class:`list` type is an example of something called a *generic type*: it can
accept one or more *type parameters*. In this case, we *parameterized* :py:class:`list`
by writing ``list[str]``. This lets mypy know that ``greet_all`` accepts specifically
lists containing strings, and not lists containing ints or any other type.

In Python 3.8 and earlier, you can instead import the
:py:class:`~typing.List` type from the :py:mod:`typing` module:

.. code-block:: python

   from typing import List  # Python 3.8 and earlier

   def greet_all(names: List[str]) -> None:
       for name in names:
           print('Hello ' + name)

   ...

You can find many of these more complex static types in the :py:mod:`typing` module.

In the above examples, the type signature is perhaps a little too rigid.
After all, there's no reason why this function must accept *specifically* a list --
it would run just fine if you were to pass in a tuple, a set, or any other custom iterable.

You can express this idea using the
:py:class:`collections.abc.Iterable` (or :py:class:`typing.Iterable` in Python
3.8 and earlier) type instead of :py:class:`list` :

.. code-block:: python

   from collections.abc import Iterable  # or "from typing import Iterable"

   def greet_all(names: Iterable[str]) -> None:
       for name in names:
           print('Hello ' + name)

As another example, suppose you want to write a function that can accept *either*
ints or strings, but no other types. You can express this using the :py:data:`~typing.Union` type:

.. code-block:: python

   from typing import Union

   def normalize_id(user_id: Union[int, str]) -> str:
       if isinstance(user_id, int):
           return f'user-{100_000 + user_id}'
       else:
           return user_id

Similarly, suppose that you want the function to accept only strings or ``None``. You can
again use :py:data:`~typing.Union` and use ``Union[str, None]`` -- or alternatively, use the type
``Optional[str]``. These two types are identical and interchangeable: ``Optional[str]``
is just a shorthand or *alias* for ``Union[str, None]``. It exists mostly as a convenience
to help function signatures look a little cleaner:

.. code-block:: python

   from typing import Optional

   def greeting(name: Optional[str] = None) -> str:
       # Optional[str] means the same thing as Union[str, None]
       if name is None:
           name = 'stranger'
       return 'Hello, ' + name

The :py:mod:`typing` module contains many other useful types. You can find a
quick overview by looking through the :ref:`mypy cheatsheet <cheat-sheet-py3>`
and a more detailed overview (including information on how to make your own
generic types or your own type aliases) by looking through the
:ref:`type system reference <overview-type-system-reference>`.

.. note::

   When adding types, the convention is to import types
   using the form ``from typing import Union`` (as opposed to doing
   just ``import typing`` or ``import typing as t`` or ``from typing import *``).

   For brevity, we often omit imports from :py:mod:`typing` or :py:mod:`collections.abc`
   in code examples, but mypy will give an error if you use types such as
   :py:class:`~typing.Iterable` without first importing them.

.. note::

   In some examples we use capitalized variants of types, such as
   ``List``, and sometimes we use plain ``list``. They are equivalent,
   but the prior variant is needed if you are using Python 3.8 or earlier.

Local type inference
********************

Once you have added type hints to a function (i.e. made it statically typed),
mypy will automatically type check that function's body. While doing so,
mypy will try and *infer* as many details as possible.

We saw an example of this in the ``normalize_id`` function above -- mypy understands
basic :py:func:`isinstance <isinstance>` checks and so can infer that the ``user_id`` variable was of
type ``int`` in the if-branch and of type ``str`` in the else-branch. Similarly, mypy
was able to understand that ``name`` could not possibly be ``None`` in the ``greeting``
function above, based both on the ``name is None`` check and the variable assignment
in that if statement.

As another example, consider the following function. Mypy can type check this function
without a problem: it will use the available context and deduce that ``output`` must be
of type ``list[float]`` and that ``num`` must be of type ``float``:

.. code-block:: python

   def nums_below(numbers: Iterable[float], limit: float) -> list[float]:
       output = []
       for num in numbers:
           if num < limit:
               output.append(num)
       return output

Mypy will warn you if it is unable to determine the type of some variable --
for example, when assigning an empty dictionary to some global value:

.. code-block:: python

    my_global_dict = {}  # Error: Need type annotation for "my_global_dict"

You can teach mypy what type ``my_global_dict`` is meant to have by giving it
a type hint. For example, if you knew this variable is supposed to be a dict
of ints to floats, you could annotate it using either variable annotations
(introduced in Python 3.6 by :pep:`526`) or using a comment-based
syntax like so:

.. code-block:: python

   # If you're using Python 3.9+
   my_global_dict: dict[int, float] = {}

   # If you're using Python 3.6+
   my_global_dict: Dict[int, float] = {}


Types and classes
*****************

So far, we've only seen examples of pre-existing types like the ``int``
or ``float`` builtins, or generic types from ``collections.abc`` and
``typing``, such as ``Iterable``. However, these aren't the only types you can
use: in fact, you can use any Python class as a type!

For example, suppose you've defined a custom class representing a bank account:

.. code-block:: python

    class BankAccount:
        # Note: It is ok to omit type hints for the "self" parameter.
        # Mypy will infer the correct type.

        def __init__(self, account_name: str, initial_balance: int = 0) -> None:
            # Note: Mypy will infer the correct types of your fields
            # based on the types of the parameters.
            self.account_name = account_name
            self.balance = initial_balance

        def deposit(self, amount: int) -> None:
            self.balance += amount

        def withdraw(self, amount: int) -> None:
            self.balance -= amount

        def overdrawn(self) -> bool:
            return self.balance < 0

You can declare that a function will accept any instance of your class
by simply annotating the parameters with ``BankAccount``:

.. code-block:: python

    def transfer(src: BankAccount, dst: BankAccount, amount: int) -> None:
        src.withdraw(amount)
        dst.deposit(amount)

    account_1 = BankAccount('Alice', 400)
    account_2 = BankAccount('Bob', 200)
    transfer(account_1, account_2, 50)

In fact, the ``transfer`` function we wrote above can accept more then just
instances of ``BankAccount``: it can also accept any instance of a *subclass*
of ``BankAccount``. For example, suppose you write a new class that looks like this:

.. code-block:: python

    class AuditedBankAccount(BankAccount):
        def __init__(self, account_name: str, initial_balance: int = 0) -> None:
            super().__init__(account_name, initial_balance)
            self.audit_log: list[str] = []

        def deposit(self, amount: int) -> None:
            self.audit_log.append(f"Deposited {amount}")
            self.balance += amount

        def withdraw(self, amount: int) -> None:
            self.audit_log.append(f"Withdrew {amount}")
            self.balance -= amount

Since ``AuditedBankAccount`` is a subclass of ``BankAccount``, we can directly pass
in instances of it into our ``transfer`` function:

.. code-block:: python

    audited = AuditedBankAccount('Charlie', 300)
    transfer(account_1, audited, 100)   # Type checks!

This behavior is actually a fundamental aspect of the PEP 484 type system: when
we annotate some variable with a type ``T``, we are actually telling mypy that
variable can be assigned an instance of ``T``, or an instance of a *subclass* of ``T``.
The same rule applies to type hints on parameters or fields.

See :ref:`class-basics` to learn more about how to work with code involving classes.


.. _stubs-intro:

Stubs files and typeshed
************************

Mypy also understands how to work with classes found in the standard library.
For example, here is a function which uses the ``Path`` object from the
`pathlib standard library module <https://docs.python.org/3/library/pathlib.html>`_:

.. code-block:: python

    from pathlib import Path

    def load_template(template_path: Path, name: str) -> str:
        # Mypy understands that 'file_path.read_text()' returns a str...
        template = template_path.read_text()

        # ...so understands this line type checks.
        return template.replace('USERNAME', name)

This behavior may surprise you if you're familiar with how
Python internally works. The standard library does not use type hints
anywhere, so how did mypy know that ``Path.read_text()`` returns a ``str``,
or that ``str.replace(...)`` accepts exactly two ``str`` arguments?

The answer is that mypy comes bundled with *stub files* from the
the `typeshed <https://github.com/python/typeshed>`_ project, which
contains stub files for the Python builtins, the standard library,
and selected third-party packages.

A *stub file* is a file containing a skeleton of the public interface
of that Python module, including classes, variables, functions -- and
most importantly, their types.

Mypy complains if it can't find a stub (or a real module) for a
library module that you import. Some modules ship with stubs or inline
annotations that mypy can automatically find, or you can install
additional stubs using pip (see :ref:`fix-missing-imports` and
:ref:`installed-packages` for the details). For example, you can install
the stubs for the ``requests`` package like this:

.. code-block:: shell

  $ python3 -m pip install types-requests

The stubs are usually packaged in a distribution named
``types-<distribution>``.  Note that the distribution name may be
different from the name of the package that you import. For example,
``types-PyYAML`` contains stubs for the ``yaml`` package. Mypy can
often suggest the name of the stub distribution:

.. code-block:: text

  prog.py:1: error: Library stubs not installed for "yaml" (or incompatible with Python 3.8)
  prog.py:1: note: Hint: "python3 -m pip install types-PyYAML"
  ...

You can also :ref:`create
stubs <stub-files>` easily. We discuss strategies for handling errors
about missing stubs in :ref:`ignore-missing-imports`.

Configuring mypy
****************

Mypy supports many command line options that you can use to tweak how
mypy behaves: see :ref:`command-line` for more details.

For example, suppose you want to make sure *all* functions within your
codebase are using static typing and make mypy report an error if you
add a dynamically-typed function by mistake. You can make mypy do this
by running mypy with the :option:`--disallow-untyped-defs <mypy --disallow-untyped-defs>` flag.

Another potentially useful flag is :option:`--strict <mypy --strict>`, which enables many
(though not all) of the available strictness options -- including
:option:`--disallow-untyped-defs <mypy --disallow-untyped-defs>`.

This flag is mostly useful if you're starting a new project from scratch
and want to maintain a high degree of type safety from day one. However,
this flag will probably be too aggressive if you either plan on using
many untyped third party libraries or are trying to add static types to
a large, existing codebase. See :ref:`existing-code` for more suggestions
on how to handle the latter case.

Next steps
**********

If you are in a hurry and don't want to read lots of documentation
before getting started, here are some pointers to quick learning
resources:

* Read the :ref:`mypy cheatsheet <cheat-sheet-py3>`.

* Read :ref:`existing-code` if you have a significant existing
  codebase without many type annotations.

* Read the `blog post <https://blog.zulip.org/2016/10/13/static-types-in-python-oh-mypy/>`_
  about the Zulip project's experiences with adopting mypy.

* If you prefer watching talks instead of reading, here are
  some ideas:

  * Carl Meyer:
    `Type Checked Python in the Real World <https://www.youtube.com/watch?v=pMgmKJyWKn8>`_
    (PyCon 2018)

  * Greg Price:
    `Clearer Code at Scale: Static Types at Zulip and Dropbox <https://www.youtube.com/watch?v=0c46YHS3RY8>`_
    (PyCon 2018)

* Look at :ref:`solutions to common issues <common_issues>` with mypy if
  you encounter problems.

* You can ask questions about mypy in the
  `mypy issue tracker <https://github.com/python/mypy/issues>`_ and
  typing `Gitter chat <https://gitter.im/python/typing>`_.

You can also continue reading this document and skip sections that
aren't relevant for you. You don't need to read sections in order.
