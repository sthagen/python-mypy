"""Script to build compiled binary wheels that can be uploaded to PyPI.

The main GitHub workflow where this script is used:
https://github.com/mypyc/mypy_mypyc-wheels/blob/master/.github/workflows/build.yml

This uses cibuildwheel (https://github.com/pypa/cibuildwheel) to build the wheels.

Usage:

  build_wheel.py --python-version <python-version> --output-dir <dir>

Wheels for the given Python version will be created in the given directory.
Python version is in form "39".

This works on macOS, Windows and Linux.

You can test locally by using --extra-opts. macOS example:

  mypy/misc/build_wheel.py --python-version 39 --output-dir out --extra-opts="--platform macos"
"""

import argparse
import os
import subprocess
from typing import Dict

# Clang package we use on Linux
LLVM_URL = 'https://github.com/mypyc/mypy_mypyc-wheels/releases/download/llvm/llvm-centos-5.tar.gz'

# Mypy repository root
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))


def create_environ(python_version: str) -> Dict[str, str]:
    """Set up environment variables for cibuildwheel."""
    env = os.environ.copy()

    env['CIBW_BUILD'] = f"cp{python_version}-*"

    # Don't build 32-bit wheels
    env['CIBW_SKIP'] = "*-manylinux_i686 *-win32 *-musllinux_*"

    # Apple Silicon support
    # When cross-compiling on Intel, it is not possible to test arm64 and
    # the arm64 part of a universal2 wheel. Warnings will be silenced with
    # following CIBW_TEST_SKIP
    env['CIBW_ARCHS_MACOS'] = "x86_64 arm64 universal2"
    env['CIBW_TEST_SKIP'] = "*-macosx_arm64 *_universal2:arm64"

    env['CIBW_BUILD_VERBOSITY'] = '1'

    # mypy's isolated builds don't specify the requirements mypyc needs, so install
    # requirements and don't use isolated builds. we need to use build-requirements.txt
    # with recent mypy commits to get stub packages needed for compilation.
    env['CIBW_BEFORE_BUILD'] = """
      pip install -r {package}/build-requirements.txt
    """.replace('\n', ' ')

    # download a copy of clang to use to compile on linux. this was probably built in 2018,
    # speeds up compilation 2x
    env['CIBW_BEFORE_BUILD_LINUX'] = """
      (cd / && curl -L %s | tar xzf -) &&
      pip install -r {package}/build-requirements.txt
    """.replace('\n', ' ') % LLVM_URL

    # the double negative is counterintuitive, https://github.com/pypa/pip/issues/5735
    env['CIBW_ENVIRONMENT'] = 'MYPY_USE_MYPYC=1 MYPYC_OPT_LEVEL=3 PIP_NO_BUILD_ISOLATION=no'
    env['CIBW_ENVIRONMENT_LINUX'] = (
        'MYPY_USE_MYPYC=1 MYPYC_OPT_LEVEL=3 PIP_NO_BUILD_ISOLATION=no ' +
        'CC=/opt/llvm/bin/clang'
    )
    env['CIBW_ENVIRONMENT_WINDOWS'] = (
        'MYPY_USE_MYPYC=1 MYPYC_OPT_LEVEL=2 PIP_NO_BUILD_ISOLATION=no'
    )

    # lxml doesn't have a wheel for Python 3.10 on the manylinux image we use.
    # lxml has historically been slow to support new Pythons as well.
    env['CIBW_BEFORE_TEST'] = """
      (
      grep -v lxml {project}/mypy/test-requirements.txt > /tmp/test-requirements.txt
      && cp {project}/mypy/mypy-requirements.txt /tmp/mypy-requirements.txt
      && cp {project}/mypy/build-requirements.txt /tmp/build-requirements.txt
      && pip install -r /tmp/test-requirements.txt
      )
    """.replace('\n', ' ')
    # lxml currently has wheels on Windows and doesn't have grep, so special case
    env['CIBW_BEFORE_TEST_WINDOWS'] = "pip install -r {project}/mypy/test-requirements.txt"

    # pytest looks for configuration files in the parent directories of where the tests live.
    # since we are trying to run the tests from their installed location, we copy those into
    # the venv. Ew ew ew.
    # We don't run external mypyc tests since there's some issue with compilation on the
    # manylinux image we use.
    env['CIBW_TEST_COMMAND'] = """
      (
      DIR=$(python -c 'import mypy, os; dn = os.path.dirname; print(dn(dn(mypy.__path__[0])))')
      && cp '{project}/mypy/pytest.ini' '{project}/mypy/conftest.py' $DIR

      && MYPY_TEST_DIR=$(python -c 'import mypy.test; print(mypy.test.__path__[0])')
      && MYPY_TEST_PREFIX='{project}/mypy' pytest $MYPY_TEST_DIR

      && MYPYC_TEST_DIR=$(python -c 'import mypyc.test; print(mypyc.test.__path__[0])')
      && MYPY_TEST_PREFIX='{project}/mypy' pytest $MYPYC_TEST_DIR -k 'not test_external'
      )
    """.replace('\n', ' ')

    # i ran into some flaky tests on windows, so only run testcheck. it looks like we
    # previously didn't run any tests on windows wheels, so this is a net win.
    env['CIBW_TEST_COMMAND_WINDOWS'] = """
      bash -c "
      (
      DIR=$(python -c 'import mypy, os; dn = os.path.dirname; print(dn(dn(mypy.__path__[0])))')
      && cp '{project}/mypy/pytest.ini' '{project}/mypy/conftest.py' $DIR

      && MYPY_TEST_DIR=$(python -c 'import mypy.test; print(mypy.test.__path__[0])')
      && MYPY_TEST_PREFIX='{project}/mypy' pytest $MYPY_TEST_DIR/testcheck.py
      )
      "
    """.replace('\n', ' ')
    return env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--python-version', required=True, metavar='XY',
                        help='Python version (e.g. 38 or 39)')
    parser.add_argument('--output-dir', required=True, metavar='DIR',
                        help='Output directory for created wheels')
    parser.add_argument('--extra-opts', default='', metavar='OPTIONS',
                        help='Extra options passed to cibuildwheel verbatim')
    args = parser.parse_args()
    python_version = args.python_version
    output_dir = args.output_dir
    extra_opts = args.extra_opts
    environ = create_environ(python_version)
    script = f'python -m cibuildwheel {extra_opts} --output-dir {output_dir} {ROOT_DIR}'
    subprocess.check_call(script, shell=True, env=environ)


if __name__ == '__main__':
    main()
