# The source directory follows Centaur's hyphenated tool-slug convention and
# Hatch maps it to ``centaur_tool_ambush_streams`` in the built package.
# ruff: noqa: N999

"""Ambush Streams tool package for Centaur."""

from .client import AmbushStreamsClient

__all__ = ["AmbushStreamsClient"]
