from django.core.management.base import BaseCommand
from django.utils import timezone
from cofinance.models import RepaymentScheduleItem, InsurancePolicy, Notification
from decimal import Decimal

class Command(BaseCommand):
    help = 'Vérifie les échéances de remboursement et les expirations d\'assurance pour envoyer des alertes.'

    def handle(self, *args, **options):
        today = timezone.now().date()
        self.stdout.write(f"Vérification des alertes pour la date du jour : {today}...")

        # ==========================================
        # 1. RAPPEL ÉCHÉANCE J-3
        # ==========================================
        target_j3 = today + timezone.timedelta(days=3)
        reminders_j3 = RepaymentScheduleItem.objects.filter(
            due_date=target_j3,
            status='pending'
        )
        j3_count = 0
        for item in reminders_j3:
            # Create J-3 Notification
            Notification.objects.create(
                user=item.credit_request.client,
                event_type='reminder_j3',
                message=f"Rappel : Votre échéance #{item.number} d'un montant de {item.amount_due} FCFA arrive à échéance le {item.due_date}."
            )
            j3_count += 1
        
        self.stdout.write(self.style.SUCCESS(f"{j3_count} rappels J-3 envoyés."))

        # ==========================================
        # 2. ALERTES RETARDS J+1 ET APPLICATION DES PÉNALITÉS
        # ==========================================
        overdue_items = RepaymentScheduleItem.objects.filter(
            due_date__lt=today
        ).exclude(status='paid')
        
        overdue_count = 0
        penalty_count = 0
        for item in overdue_items:
            # Check delay in days
            delay = (today - item.due_date).days
            
            # Apply daily penalty rate: 2% of amount_due per day of delay
            old_penalties = item.penalties_accumulated
            new_penalties = (item.amount_due * Decimal('0.02') * Decimal(str(delay))).quantize(Decimal('0.01'))
            item.penalties_accumulated = new_penalties
            
            # Transition status to overdue if it was pending
            if item.status == 'pending':
                item.status = 'overdue'
                overdue_count += 1
                
            item.save()
            penalty_count += 1

            # Dispatch notification on J+1 (or if it just transitioned to overdue)
            if delay == 1:
                Notification.objects.create(
                    user=item.credit_request.client,
                    event_type='overdue_j1',
                    message=f"Alerte retard : Votre échéance #{item.number} du crédit #{item.credit_request.id} est en retard. Des pénalités journalières de 2% ont commencé à s'accumuler (Pénalités actuelles : {item.penalties_accumulated} FCFA)."
                )

        self.stdout.write(self.style.SUCCESS(f"{overdue_count} échéances marquées EN RETARD. {penalty_count} pénalités mises à jour."))

        # ==========================================
        # 3. EXPIRATION ASSURANCE J-15
        # ==========================================
        target_j15 = today + timezone.timedelta(days=15)
        expiring_policies = InsurancePolicy.objects.filter(
            end_date=target_j15,
            status='active'
        )
        j15_count = 0
        for policy in expiring_policies:
            Notification.objects.create(
                user=policy.client,
                event_type='insurance_expiring',
                message=f"Alerte assurance : Votre police d'assurance '{policy.product.name}' expire le {policy.end_date} (dans 15 jours). Veuillez renouveler votre souscription."
            )
            j15_count += 1

        self.stdout.write(self.style.SUCCESS(f"{j15_count} alertes d'expiration d'assurance J-15 envoyées."))
        
        # ==========================================
        # 4. MISE À JOUR GÉNÉRALE DE STATUT DES POLICES EXPIRÉES
        # ==========================================
        expired_policies = InsurancePolicy.objects.filter(
            end_date__lt=today,
            status='active'
        )
        expired_count = 0
        for policy in expired_policies:
            policy.status = 'expired'
            policy.save()
            expired_count += 1
            
        self.stdout.write(self.style.SUCCESS(f"{expired_count} polices d'assurance expirées mises à jour."))
