from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from .models import (
    CreditRequest, CreditDocument, RepaymentScheduleItem, 
    Repayment, InsuranceProduct, InsurancePolicy, Notification, 
    Conversation, Message
)
from decimal import Decimal

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone', 'region', 'monthly_income', 'address', 'registration_date')
        read_only_fields = ('id', 'role', 'registration_date')


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'first_name', 'last_name', 'phone', 'region', 'monthly_income', 'address')

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        validated_data['role'] = 'client'  # Self-registration defaults to client
        return super().create(validated_data)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class CreditDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditDocument
        fields = ('id', 'file', 'uploaded_at')


class RepaymentScheduleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RepaymentScheduleItem
        fields = ('id', 'number', 'due_date', 'amount_due', 'amount_paid', 'status', 'penalties_accumulated')


class CreditRequestSerializer(serializers.ModelSerializer):
    client = UserSerializer(read_only=True)
    documents = CreditDocumentSerializer(many=True, read_only=True)
    schedule = RepaymentScheduleItemSerializer(many=True, read_only=True)
    uploaded_files = serializers.ListField(
        child=serializers.FileField(max_length=100000, allow_empty_file=False, use_url=False),
        write_only=True,
        required=False
    )

    class Meta:
        model = CreditRequest
        fields = (
            'id', 'client', 'amount_requested', 'duration_months', 
            'repayment_frequency', 'interest_rate', 'status', 
            'eligibility_score', 'assigned_agent', 'approved_by', 
            'created_at', 'updated_at', 'documents', 'schedule', 'uploaded_files'
        )
        read_only_fields = ('id', 'interest_rate', 'status', 'eligibility_score', 'assigned_agent', 'approved_by', 'created_at', 'updated_at')

    def create(self, validated_data):
        uploaded_files = validated_data.pop('uploaded_files', [])
        # Get request user from context
        request = self.context.get('request')
        validated_data['client'] = request.user
        
        # Interest rate: default configuration can be 5.0%
        validated_data['interest_rate'] = Decimal('5.00')
        
        credit_request = CreditRequest.objects.create(**validated_data)
        
        for file in uploaded_files:
            CreditDocument.objects.create(credit_request=credit_request, file=file)
            
        return credit_request


class RepaymentSerializer(serializers.ModelSerializer):
    recorded_by = UserSerializer(read_only=True)
    
    class Meta:
        model = Repayment
        fields = ('id', 'schedule_item', 'amount', 'paid_at', 'recorded_by')
        read_only_fields = ('id', 'paid_at', 'recorded_by')

    def validate(self, data):
        schedule_item = data['schedule_item']
        if schedule_item.status == 'paid':
            raise serializers.ValidationError("Cette échéance est déjà entièrement payée.")
        
        remaining = (schedule_item.amount_due + schedule_item.penalties_accumulated) - schedule_item.amount_paid
        if data['amount'] <= 0:
            raise serializers.ValidationError("Le montant du remboursement doit être supérieur à 0.")
            
        return data


class InsuranceProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceProduct
        fields = ('id', 'name', 'description', 'duration_months', 'premium', 'conditions')


class InsurancePolicySerializer(serializers.ModelSerializer):
    client = UserSerializer(read_only=True)
    product_detail = InsuranceProductSerializer(source='product', read_only=True)
    product = serializers.PrimaryKeyRelatedField(queryset=InsuranceProduct.objects.all(), write_only=True)

    class Meta:
        model = InsurancePolicy
        fields = ('id', 'client', 'product', 'product_detail', 'start_date', 'end_date', 'status')
        read_only_fields = ('id', 'start_date', 'end_date', 'status')

    def create(self, validated_data):
        request = self.context.get('request')
        client = request.user
        product = validated_data['product']
        
        # Check if already active policy for the same product
        active_exists = InsurancePolicy.objects.filter(
            client=client,
            product=product,
            status='active'
        ).exists()
        if active_exists:
            raise serializers.ValidationError("Vous avez déjà une souscription active pour cette formule d'assurance.")

        start_date = timezone.now().date()
        # End date is start_date + product duration_months
        # A simple approximation or exact months addition
        # Let's approximate: 1 month = 30 days
        end_date = start_date + timezone.timedelta(days=product.duration_months * 30)
        
        policy = InsurancePolicy.objects.create(
            client=client,
            product=product,
            start_date=start_date,
            end_date=end_date,
            status='active'
        )
        return policy


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'event_type', 'message', 'is_read', 'created_at')
        read_only_fields = ('id', 'event_type', 'message', 'created_at')


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.username', read_only=True)
    sender_role = serializers.CharField(source='sender.role', read_only=True)

    class Meta:
        model = Message
        fields = ('id', 'conversation', 'sender', 'sender_name', 'sender_role', 'content', 'created_at')
        read_only_fields = ('id', 'sender', 'created_at')


class ConversationSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.username', read_only=True)
    agent_name = serializers.CharField(source='agent.username', default="Non assigné", read_only=True)
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ('id', 'client', 'client_name', 'agent', 'agent_name', 'status', 'created_at', 'updated_at', 'last_message')
        read_only_fields = ('id', 'client', 'created_at', 'updated_at')

    def get_last_message(self, obj):
        msg = obj.messages.order_by('-created_at').first()
        if msg:
            return {
                'content': msg.content,
                'sender': msg.sender.username,
                'created_at': msg.created_at
            }
        return None
