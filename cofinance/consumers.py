import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Conversation, Message
from .serializers import MessageSerializer

User = get_user_model()

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'chat_{self.conversation_id}'
        self.user = self.scope.get('user')

        # 1. Authenticate user
        if not self.user or self.user.is_anonymous:
            await self.close(code=4003)  # Unauthorized
            return

        # 2. Check permissions
        is_allowed = await self.check_permissions()
        if not is_allowed:
            await self.close(code=4003)  # Forbidden
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Broadcast online status to the group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'presence_broadcast',
                'user': self.user.username,
                'role': self.user.role,
                'status': 'online'
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            # Broadcast offline status to the group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'presence_broadcast',
                    'user': self.user.username,
                    'role': self.user.role,
                    'status': 'offline'
                }
            )
            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content, **kwargs):
        action = content.get('action')
        
        if action == 'message':
            msg_content = content.get('content', '').strip()
            if msg_content:
                # Save to database
                msg_data = await self.save_message(msg_content)
                # Broadcast message to group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message_broadcast',
                        'message': msg_data
                    }
                )
        elif action == 'typing':
            is_typing = content.get('is_typing', False)
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'typing_broadcast',
                    'user': self.user.username,
                    'is_typing': is_typing
                }
            )

    # Handlers for group messages
    async def chat_message_broadcast(self, event):
        await self.send_json({
            'type': 'message',
            'message': event['message']
        })

    async def typing_broadcast(self, event):
        # Don't send typing status back to the sender
        if event['user'] != self.user.username:
            await self.send_json({
                'type': 'typing',
                'user': event['user'],
                'is_typing': event['is_typing']
            })

    async def presence_broadcast(self, event):
        await self.send_json({
            'type': 'presence',
            'user': event['user'],
            'role': event['role'],
            'status': event['status']
        })

    # Database query helpers
    @database_sync_to_async
    def check_permissions(self):
        try:
            conv = Conversation.objects.get(id=self.conversation_id)
            # Agents, admins and owners are allowed
            if self.user.role in ['admin', 'agent'] or self.user.is_superuser:
                return True
            if conv.client == self.user:
                return True
            return False
        except Conversation.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, content):
        conv = Conversation.objects.get(id=self.conversation_id)
        msg = Message.objects.create(
            conversation=conv,
            sender=self.user,
            content=content
        )
        serializer = MessageSerializer(msg)
        return serializer.data
