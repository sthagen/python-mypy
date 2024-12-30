from __future__ import annotations


def is_module_from_legacy_bundled_package(module: str) -> bool:
    top_level = module.split(".", 1)[0]
    return top_level in legacy_bundled_packages


def stub_distribution_name(module: str) -> str | None:
    top_level = module.split(".", 1)[0]

    dist = legacy_bundled_packages.get(top_level)
    if dist:
        return dist
    dist = non_bundled_packages_flat.get(top_level)
    if dist:
        return dist

    if top_level in non_bundled_packages_namespace:
        namespace = non_bundled_packages_namespace[top_level]
        components = module.split(".")
        for i in range(len(components), 0, -1):
            module = ".".join(components[:i])
            dist = namespace.get(module)
            if dist:
                return dist

    return None


# Stubs for these third-party packages used to be shipped with mypy.
#
# Map package name to PyPI stub distribution name.
legacy_bundled_packages: dict[str, str] = {
    "aiofiles": "types-aiofiles",
    "bleach": "types-bleach",
    "boto": "types-boto",
    "cachetools": "types-cachetools",
    "click_spinner": "types-click-spinner",
    "contextvars": "types-contextvars",
    "croniter": "types-croniter",
    "dataclasses": "types-dataclasses",
    "dateparser": "types-dateparser",
    "dateutil": "types-python-dateutil",
    "decorator": "types-decorator",
    "deprecated": "types-Deprecated",
    "docutils": "types-docutils",
    "first": "types-first",
    "gflags": "types-python-gflags",
    "markdown": "types-Markdown",
    "mock": "types-mock",
    "OpenSSL": "types-pyOpenSSL",
    "paramiko": "types-paramiko",
    "pkg_resources": "types-setuptools",
    "polib": "types-polib",
    "pycurl": "types-pycurl",
    "pymysql": "types-PyMySQL",
    "pyrfc3339": "types-pyRFC3339",
    "python2": "types-six",
    "pytz": "types-pytz",
    "pyVmomi": "types-pyvmomi",
    "redis": "types-redis",
    "requests": "types-requests",
    "retry": "types-retry",
    "simplejson": "types-simplejson",
    "singledispatch": "types-singledispatch",
    "six": "types-six",
    "slugify": "types-python-slugify",
    "tabulate": "types-tabulate",
    "toml": "types-toml",
    "typed_ast": "types-typed-ast",
    "tzlocal": "types-tzlocal",
    "ujson": "types-ujson",
    "waitress": "types-waitress",
    "yaml": "types-PyYAML",
}

# Map package name to PyPI stub distribution name from typeshed.
# Stubs for these packages were never bundled with mypy. Don't
# include packages that have a release that includes PEP 561 type
# information.
#
# Note that these packages are omitted for now:
#   pika:       typeshed's stubs are on PyPI as types-pika-ts.
#               types-pika already exists on PyPI, and is more complete in many ways,
#               but is a non-typeshed stubs package.
non_bundled_packages_flat: dict[str, str] = {
    "_cffi_backend": "types-cffi",
    "_win32typing": "types-pywin32",
    "antlr4": "types-antlr4-python3-runtime",
    "assertpy": "types-assertpy",
    "atheris": "types-atheris",
    "authlib": "types-Authlib",
    "aws_xray_sdk": "types-aws-xray-sdk",
    "babel": "types-babel",
    "boltons": "types-boltons",
    "braintree": "types-braintree",
    "bs4": "types-beautifulsoup4",
    "bugbear": "types-flake8-bugbear",
    "caldav": "types-caldav",
    "capturer": "types-capturer",
    "cffi": "types-cffi",
    "chevron": "types-chevron",
    "click_default_group": "types-click-default-group",
    "click_log": "types-click-log",
    "click_web": "types-click-web",
    "colorama": "types-colorama",
    "commctrl": "types-pywin32",
    "commonmark": "types-commonmark",
    "consolemenu": "types-console-menu",
    "corus": "types-corus",
    "cronlog": "types-python-crontab",
    "crontab": "types-python-crontab",
    "crontabs": "types-python-crontab",
    "d3dshot": "types-D3DShot",
    "datemath": "types-python-datemath",
    "dateparser_data": "types-dateparser",
    "dde": "types-pywin32",
    "defusedxml": "types-defusedxml",
    "docker": "types-docker",
    "dockerfile_parse": "types-dockerfile-parse",
    "docopt": "types-docopt",
    "editdistance": "types-editdistance",
    "entrypoints": "types-entrypoints",
    "exifread": "types-ExifRead",
    "fanstatic": "types-fanstatic",
    "farmhash": "types-pyfarmhash",
    "flake8_2020": "types-flake8-2020",
    "flake8_builtins": "types-flake8-builtins",
    "flake8_docstrings": "types-flake8-docstrings",
    "flake8_plugin_utils": "types-flake8-plugin-utils",
    "flake8_rst_docstrings": "types-flake8-rst-docstrings",
    "flake8_simplify": "types-flake8-simplify",
    "flake8_typing_imports": "types-flake8-typing-imports",
    "flake8": "types-flake8",
    "flask_cors": "types-Flask-Cors",
    "flask_migrate": "types-Flask-Migrate",
    "flask_socketio": "types-Flask-SocketIO",
    "fpdf": "types-fpdf2",
    "gdb": "types-gdb",
    "gevent": "types-gevent",
    "greenlet": "types-greenlet",
    "hdbcli": "types-hdbcli",
    "html5lib": "types-html5lib",
    "httplib2": "types-httplib2",
    "humanfriendly": "types-humanfriendly",
    "hvac": "types-hvac",
    "ibm_db": "types-ibm-db",
    "icalendar": "types-icalendar",
    "import_export": "types-django-import-export",
    "influxdb_client": "types-influxdb-client",
    "inifile": "types-inifile",
    "invoke": "types-invoke",
    "isapi": "types-pywin32",
    "jack": "types-JACK-Client",
    "jenkins": "types-python-jenkins",
    "Jetson": "types-Jetson.GPIO",
    "jks": "types-pyjks",
    "jmespath": "types-jmespath",
    "jose": "types-python-jose",
    "jsonschema": "types-jsonschema",
    "jwcrypto": "types-jwcrypto",
    "keyboard": "types-keyboard",
    "ldap3": "types-ldap3",
    "lupa": "types-lupa",
    "lzstring": "types-lzstring",
    "m3u8": "types-m3u8",
    "mmapfile": "types-pywin32",
    "mmsystem": "types-pywin32",
    "mypy_extensions": "types-mypy-extensions",
    "MySQLdb": "types-mysqlclient",
    "nanoid": "types-nanoid",
    "nanoleafapi": "types-nanoleafapi",
    "netaddr": "types-netaddr",
    "netifaces": "types-netifaces",
    "networkx": "types-networkx",
    "nmap": "types-python-nmap",
    "ntsecuritycon": "types-pywin32",
    "oauthlib": "types-oauthlib",
    "objgraph": "types-objgraph",
    "odbc": "types-pywin32",
    "olefile": "types-olefile",
    "openpyxl": "types-openpyxl",
    "opentracing": "types-opentracing",
    "parsimonious": "types-parsimonious",
    "passlib": "types-passlib",
    "passpy": "types-passpy",
    "peewee": "types-peewee",
    "pep8ext_naming": "types-pep8-naming",
    "perfmon": "types-pywin32",
    "pexpect": "types-pexpect",
    "PIL": "types-Pillow",
    "playhouse": "types-peewee",
    "playsound": "types-playsound",
    "portpicker": "types-portpicker",
    "psutil": "types-psutil",
    "psycopg2": "types-psycopg2",
    "pyasn1": "types-pyasn1",
    "pyaudio": "types-pyaudio",
    "pyautogui": "types-PyAutoGUI",
    "pycocotools": "types-pycocotools",
    "pyflakes": "types-pyflakes",
    "pygit2": "types-pygit2",
    "pygments": "types-Pygments",
    "pyi_splash": "types-pyinstaller",
    "PyInstaller": "types-pyinstaller",
    "pynput": "types-pynput",
    "pyscreeze": "types-PyScreeze",
    "pysftp": "types-pysftp",
    "pytest_lazyfixture": "types-pytest-lazy-fixture",
    "python_http_client": "types-python-http-client",
    "pythoncom": "types-pywin32",
    "pythonwin": "types-pywin32",
    "pywintypes": "types-pywin32",
    "qrbill": "types-qrbill",
    "qrcode": "types-qrcode",
    "regex": "types-regex",
    "regutil": "types-pywin32",
    "reportlab": "types-reportlab",
    "requests_oauthlib": "types-requests-oauthlib",
    "RPi": "types-RPi.GPIO",
    "s2clientprotocol": "types-s2clientprotocol",
    "sass": "types-libsass",
    "sassutils": "types-libsass",
    "seaborn": "types-seaborn",
    "send2trash": "types-Send2Trash",
    "serial": "types-pyserial",
    "servicemanager": "types-pywin32",
    "setuptools": "types-setuptools",
    "shapely": "types-shapely",
    "slumber": "types-slumber",
    "sspicon": "types-pywin32",
    "stdlib_list": "types-stdlib-list",
    "str2bool": "types-str2bool",
    "stripe": "types-stripe",
    "tensorflow": "types-tensorflow",
    "tgcrypto": "types-TgCrypto",
    "timer": "types-pywin32",
    "toposort": "types-toposort",
    "tqdm": "types-tqdm",
    "translationstring": "types-translationstring",
    "tree_sitter_languages": "types-tree-sitter-languages",
    "tree_sitter": "types-tree-sitter",
    "ttkthemes": "types-ttkthemes",
    "unidiff": "types-unidiff",
    "untangle": "types-untangle",
    "usersettings": "types-usersettings",
    "uwsgi": "types-uWSGI",
    "uwsgidecorators": "types-uWSGI",
    "vobject": "types-vobject",
    "webob": "types-WebOb",
    "whatthepatch": "types-whatthepatch",
    "win2kras": "types-pywin32",
    "win32": "types-pywin32",
    "win32api": "types-pywin32",
    "win32clipboard": "types-pywin32",
    "win32com": "types-pywin32",
    "win32comext": "types-pywin32",
    "win32con": "types-pywin32",
    "win32console": "types-pywin32",
    "win32cred": "types-pywin32",
    "win32crypt": "types-pywin32",
    "win32cryptcon": "types-pywin32",
    "win32event": "types-pywin32",
    "win32evtlog": "types-pywin32",
    "win32evtlogutil": "types-pywin32",
    "win32file": "types-pywin32",
    "win32gui_struct": "types-pywin32",
    "win32gui": "types-pywin32",
    "win32help": "types-pywin32",
    "win32inet": "types-pywin32",
    "win32inetcon": "types-pywin32",
    "win32job": "types-pywin32",
    "win32lz": "types-pywin32",
    "win32net": "types-pywin32",
    "win32netcon": "types-pywin32",
    "win32pdh": "types-pywin32",
    "win32pdhquery": "types-pywin32",
    "win32pipe": "types-pywin32",
    "win32print": "types-pywin32",
    "win32process": "types-pywin32",
    "win32profile": "types-pywin32",
    "win32ras": "types-pywin32",
    "win32security": "types-pywin32",
    "win32service": "types-pywin32",
    "win32serviceutil": "types-pywin32",
    "win32timezone": "types-pywin32",
    "win32trace": "types-pywin32",
    "win32transaction": "types-pywin32",
    "win32ts": "types-pywin32",
    "win32ui": "types-pywin32",
    "win32uiole": "types-pywin32",
    "win32verstamp": "types-pywin32",
    "win32wnet": "types-pywin32",
    "winerror": "types-pywin32",
    "winioctlcon": "types-pywin32",
    "winnt": "types-pywin32",
    "winperf": "types-pywin32",
    "winxpgui": "types-pywin32",
    "winxptheme": "types-pywin32",
    "workalendar": "types-workalendar",
    "wtforms": "types-WTForms",
    "wurlitzer": "types-wurlitzer",
    "xdg": "types-pyxdg",
    "xdgenvpy": "types-xdgenvpy",
    "Xlib": "types-python-xlib",
    "xmltodict": "types-xmltodict",
    "zstd": "types-zstd",
    "zxcvbn": "types-zxcvbn",
    # Stub packages that are not from typeshed
    # Since these can be installed automatically via --install-types, we have a high trust bar
    # for additions here
    "pandas": "pandas-stubs",  # https://github.com/pandas-dev/pandas-stubs
    "lxml": "lxml-stubs",  # https://github.com/lxml/lxml-stubs
}


non_bundled_packages_namespace: dict[str, dict[str, str]] = {
    "backports": {"backports.ssl_match_hostname": "types-backports.ssl_match_hostname"},
    "google": {"google.cloud.ndb": "types-google-cloud-ndb", "google.protobuf": "types-protobuf"},
    "paho": {"paho.mqtt": "types-paho-mqtt"},
}
