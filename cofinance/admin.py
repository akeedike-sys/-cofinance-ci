from django.contrib import admin
from .models import User, CreditRequest, Repayment, RepaymentScheduleItem, InsuranceProduct, InsurancePolicy, Conversation, Message, CreditDocument, Notification

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'region')

@admin.register(CreditRequest)
class CreditRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'amount_requested', 'status', 'created_at')

@admin.register(InsuranceProduct)
class InsuranceProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'premium', 'duration_months')

@admin.register(InsurancePolicy)
class InsurancePolicyAdmin(admin.ModelAdmin):
    list_display = ('client', 'product', 'status', 'start_date')

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'agent', 'status')

@admin.register(Repayment)
class RepaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'schedule_item', 'amount', 'paid_at')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'event_type', 'is_read', 'created_at')
