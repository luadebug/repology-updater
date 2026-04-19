# Copyright (C) 2024 Repology contributors
#
# This file is part of repology
#
# repology is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# repology is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with repology.  If not, see <http://www.gnu.org/licenses/>.

import os
import re
from typing import Iterable

from repology.package import LinkType
from repology.packagemaker import NameType, PackageFactory, PackageMaker
from repology.parsers import Parser
from repology.parsers.walk import walk_tree


def _parse_lua_string(s: str) -> str:
    # xmake.lua uses double-quoted strings; handle basic escape sequences
    return s.replace('\\"', '"').replace('\\\\', '\\')


def _normalize_version(version: str) -> str:
    # strip leading 'v' prefix (e.g. "v1.0.0" -> "1.0.0")
    if version.startswith('v') and len(version) > 1 and version[1].isdigit():
        return version[1:]
    return version


class XrepoGitParser(Parser):
    def iter_parse(self, path: str, factory: PackageFactory) -> Iterable[PackageMaker]:
        packages_root = os.path.join(path, 'packages')
        if not os.path.isdir(packages_root):
            return

        for xmake_lua_path in walk_tree(packages_root, name='xmake.lua'):
            rel_path = os.path.relpath(xmake_lua_path, path)

            try:
                with open(xmake_lua_path, encoding='utf-8', errors='replace') as f:
                    content = f.read()
            except OSError:
                continue

            _str = r'"((?:\\.|[^"\\])*)"'

            # package name is the first argument to package()
            name_match = re.search(r'^package\s*\(\s*' + _str + r'\s*\)', content, re.MULTILINE)
            if name_match is None:
                continue
            pkgname = _parse_lua_string(name_match.group(1))

            # findall with two groups returns (version, checksum) tuples
            versions = [
                _parse_lua_string(ver)
                for ver, _ in re.findall(r'add_versions\s*\(\s*' + _str + r'\s*,\s*' + _str + r'\s*\)', content)
            ]
            if not versions:
                continue

            homepage_match = re.search(r'set_homepage\s*\(\s*' + _str + r'\s*\)', content)
            description_match = re.search(r'set_description\s*\(\s*' + _str + r'\s*\)', content)
            license_match = re.search(r'set_license\s*\(\s*' + _str + r'\s*\)', content)

            with factory.begin(rel_path) as pkg:
                pkg.add_name(pkgname, NameType.XREPO_NAME)
                pkg.set_extra_field('letter', pkgname[0].lower())
                pkg.set_extra_field('xrepo_package_path', os.path.dirname(rel_path).replace(os.sep, '/'))

                if homepage_match:
                    pkg.add_links(LinkType.UPSTREAM_HOMEPAGE, _parse_lua_string(homepage_match.group(1)))

                if description_match:
                    pkg.set_summary(_parse_lua_string(description_match.group(1)))

                if license_match:
                    pkg.add_licenses(_parse_lua_string(license_match.group(1)))

                for version in versions:
                    verpkg = pkg.clone(append_ident=':' + version)
                    verpkg.set_version(version, _normalize_version)
                    yield verpkg
