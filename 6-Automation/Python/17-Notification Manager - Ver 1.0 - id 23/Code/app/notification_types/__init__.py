from app.notification_types.date_time.handler import DateTimeNotificationType
from app.notification_types.battery.handler import BatteryNotificationType


class NotificationTypeRegistry:
    def __init__(self):
        self._types = {}

        self.register(DateTimeNotificationType())
        self.register(BatteryNotificationType())

    def register(self, notification_type):
        self._types[notification_type.type_id] = notification_type

    def get(self, type_id):
        return self._types.get(type_id)

    def all(self):
        return list(self._types.values())

    def ids(self):
        return list(self._types.keys())