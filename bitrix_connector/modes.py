"""Enumeración operativa sin dependencias para evitar ciclos de importación."""

from enum import Enum


class ConnectorMode(str, Enum):
    OFF = "off"
    REVIEW = "review"
    SHADOW = "shadow"
    ACTIVE = "active"
