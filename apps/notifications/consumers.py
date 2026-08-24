from channels.generic.websocket import AsyncJsonWebsocketConsumer


class NotificationConsumer(
    AsyncJsonWebsocketConsumer
):

    async def connect(self):

        user = self.scope["user"]

        # Reject unauthenticated users
        if not user.is_authenticated:
            await self.close()
            return

        self.group_name = f"user_{user.id}"

        # Accept connection first
        # Frontend gets "WebSocket connected" faster
        await self.accept()

        # Then join notification group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )


    async def disconnect(
        self,
        close_code,
    ):

        if hasattr(self, "group_name"):

            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name,
            )


    async def notification_message(
        self,
        event,
    ):

        await self.send_json(
            {
                "type": "notification",

                "notification_id": event[
                    "notification_id"
                ],

                "notification_type": event[
                    "notification_type"
                ],
            }
        )