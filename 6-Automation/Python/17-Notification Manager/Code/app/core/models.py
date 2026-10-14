import uuid

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Notification:
    """
    Generic notification model.

    The core application does not know what the
    notification settings mean. The notification
    extension owns the interpretation of settings.
    """

    id: str = field(
        default_factory=lambda: str(
            uuid.uuid4()
        )
    )

    type: str = ""

    title: str = ""

    message: str = ""

    enabled: bool = True

    sound_enabled: bool = True

    sound_file: str = ""

    settings: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self):
        """
        Convert notification to a JSON-compatible
        dictionary.
        """

        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "enabled": self.enabled,
            "sound_enabled": self.sound_enabled,
            "sound_file": self.sound_file,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data):
        """
        Create a Notification from saved JSON data.
        """

        return cls(
            id=data.get(
                "id",
                str(uuid.uuid4()),
            ),

            type=data.get(
                "type",
                "",
            ),

            title=data.get(
                "title",
                "",
            ),

            message=data.get(
                "message",
                "",
            ),

            enabled=data.get(
                "enabled",
                True,
            ),

            sound_enabled=data.get(
                "sound_enabled",
                True,
            ),

            sound_file=data.get(
                "sound_file",
                "",
            ),

            settings=data.get(
                "settings",
                {},
            ),
        )