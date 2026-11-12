# Copyright (C) 2024 Bastian Kleineidam
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Archive commands for the 7zzs program.
The 7zzs program is included in the Linux-specific distribution of the 7-Zip
package.
"""
# The 7zzs program is the static linked version of 7zz and has the same options.
# Therefore we import all function from the p7zz.py package.

# ruff: noqa: F403
from .p7zz import *
