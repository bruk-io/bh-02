"""Concrete probe batteries, one module per axis: env, limits, fs, network.

Deliberately not a barrel -- each battery is imported by its own module
path (`brig.probe.batteries.env`, `.limits`, `.fs`, `.network`, ...) rather
than re-exported through this file, so tasks landing separate batteries
never touch one shared module. This file carries only this docstring.
"""
