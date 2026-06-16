from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import CreditRequest, Repayment, InsurancePolicy, Notification

@receiver(pre_save, sender=CreditRequest)
def credit_request_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old_instance = CreditRequest.objects.get(pk=instance.pk)
            instance._old_status = old_instance.status
        except CreditRequest.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None

@receiver(post_save, sender=CreditRequest)
def credit_request_post_save(sender, instance, created, **kwargs):
    old_status = getattr(instance, '_old_status', None)
    
    # Send notification if status changed or newly created
    if created or old_status != instance.status:
        Notification.objects.create(
            user=instance.client,
            event_type='credit_status',
            message=f"Le statut de votre demande de crédit #{instance.id} a été mis à jour : {instance.get_status_display()}."
        )
        
        # Automatically generate repayment schedule when loan is approved
        if instance.status == 'approved' and old_status != 'approved':
            instance.generate_schedule()


@receiver(post_save, sender=Repayment)
def repayment_post_save(sender, instance, created, **kwargs):
    if created:
        item = instance.schedule_item
        item.amount_paid += instance.amount
        
        # Check if full amount (due + penalties) is met
        total_due = item.amount_due + item.penalties_accumulated
        if item.amount_paid >= total_due:
            item.status = 'paid'
        
        item.save()

        # Send repayment confirmation notification
        Notification.objects.create(
            user=item.credit_request.client,
            event_type='repayment_recorded',
            message=f"Paiement de {instance.amount} FCFA enregistré pour l'échéance #{item.number} du crédit #{item.credit_request.id}."
        )


@receiver(post_save, sender=InsurancePolicy)
def insurance_policy_post_save(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            user=instance.client,
            event_type='insurance_confirmed',
            message=f"Votre souscription au produit '{instance.product.name}' a été enregistrée. Couverture active jusqu'au {instance.end_date}."
        )
