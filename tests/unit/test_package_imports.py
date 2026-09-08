"""P0 smoke test — proves the package installs and CI is wired correctly.

Delete this once real unit tests exist for T1 (simulator) modules.
"""

import fabtwin


def test_package_has_version():
    assert fabtwin.__version__ == "0.0.0"
