from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
import datetime

from cofinance.models import (
    CreditRequest, RepaymentScheduleItem, Repayment, 
    InsuranceProduct, InsurancePolicy, Conversation, Message
)

User = get_user_model()

class Command(BaseCommand):
    help = 'Peuple la base de données avec des données de démonstration.'

    def handle(self, *args, **options):
        self.stdout.write('Purge de la base de données...')
        Message.objects.all().delete()
        Conversation.objects.all().delete()
        Repayment.objects.all().delete()
        RepaymentScheduleItem.objects.all().delete()
        CreditRequest.objects.all().delete()
        InsurancePolicy.objects.all().delete()
        InsuranceProduct.objects.all().delete()
        
        # Keep superusers if they exist, but delete regular seeded users
        User.objects.filter(email__in=[
            'admin@cofinance.ci', 'agent1@cofinance.ci', 
            'agent2@cofinance.ci', 'client1@cofinance.ci', 
            'client2@cofinance.ci'
        ]).delete()

        self.stdout.write('Création des utilisateurs...')
        
        # 1. Admin
        admin_user = User.objects.create_superuser(
            username='admin',
            email='admin@cofinance.ci',
            password='admin123',
            role='admin',
            phone='0707070707',
            region='Abidjan Plateau',
            address='Siège COFINANCE CI, Immeuble BCEAO'
        )

        # 2. Agents
        agent1 = User.objects.create_user(
            username='agent1',
            email='agent1@cofinance.ci',
            password='agent123',
            role='agent',
            phone='0505050505',
            region='Abidjan',
            address='Agence Abidjan Cocody'
        )
        
        agent2 = User.objects.create_user(
            username='agent2',
            email='agent2@cofinance.ci',
            password='agent123',
            role='agent',
            phone='0606060606',
            region='Bouake',
            address='Agence Bouaké Commerce'
        )

        # 3. Clients
        client1 = User.objects.create_user(
            username='client1',
            email='client1@cofinance.ci',
            password='client123',
            role='client',
            phone='0101010101',
            region='Abidjan',
            monthly_income=Decimal('450000.00'),
            address='Marcory Zone 4, Abidjan'
        )
        # Set registration date to 1.5 years ago for client1 to give him seniority points
        client1.registration_date = timezone.now() - datetime.timedelta(days=550)
        client1.save()

        client2 = User.objects.create_user(
            username='client2',
            email='client2@cofinance.ci',
            password='client123',
            role='client',
            phone='0202020202',
            region='Korhogo',
            monthly_income=Decimal('120000.00'),
            address='Quartier Koko, Korhogo'
        )
        # New client (registration date is now)
        client2.registration_date = timezone.now()
        client2.save()

        self.stdout.write('Création des produits d\'assurance...')
        ins1 = InsuranceProduct.objects.create(
            name='Assurance Décès-Invalidité Simplifiée',
            description='Couverture décès et invalidité absolue et définitive. Indemnité versée sous 48h.',
            duration_months=12,
            premium=Decimal('6000.00'),
            conditions='Âge entre 18 et 65 ans. Client COFINANCE CI actif.'
        )

        ins2 = InsuranceProduct.objects.create(
            name='Assurance Vie Micro-Commerçant',
            description='Garantit un capital en cas d\'hospitalisation ou d\'interruption d\'activité commerciale.',
            duration_months=6,
            premium=Decimal('3000.00'),
            conditions='Commerçant enregistré ou travailleur indépendant.'
        )

        self.stdout.write('Création des souscriptions d\'assurance...')
        # Client 1: active insurance policy
        InsurancePolicy.objects.create(
            client=client1,
            product=ins1,
            start_date=timezone.now().date() - datetime.timedelta(days=30),
            end_date=timezone.now().date() + datetime.timedelta(days=335),
            status='active'
        )

        # Client 2: insurance policy expiring in 15 days (so start date is end_date - 180 days)
        # Duration is 6 months (180 days). End date is now + 15 days. Start date is now - 165 days.
        InsurancePolicy.objects.create(
            client=client2,
            product=ins2,
            start_date=timezone.now().date() - datetime.timedelta(days=165),
            end_date=timezone.now().date() + datetime.timedelta(days=15),
            status='active'
        )

        self.stdout.write('Création des demandes de crédit...')
        # Client 1: Disbursed Credit (repayments in progress)
        c1_credit = CreditRequest.objects.create(
            client=client1,
            amount_requested=Decimal('300000.00'),
            duration_months=3,
            repayment_frequency='MENSUEL',
            interest_rate=Decimal('5.00'),
            status='disbursed',
            assigned_agent=agent1,
            approved_by=admin_user
        )
        # Create custom dates for Client 1 schedule items to test alerts:
        # Installment 1 (due 10 days ago, PAID)
        item1 = RepaymentScheduleItem.objects.create(
            credit_request=c1_credit,
            number=1,
            due_date=timezone.now().date() - datetime.timedelta(days=10),
            amount_due=Decimal('105000.00'),
            amount_paid=Decimal('105000.00'),
            status='paid'
        )
        Repayment.objects.create(
            schedule_item=item1,
            amount=Decimal('105000.00'),
            paid_at=timezone.now() - datetime.timedelta(days=10),
            recorded_by=agent1
        )
        
        # Installment 2 (due 1 day ago, UNPAID -> will be marked overdue and penalized by check_reminders)
        RepaymentScheduleItem.objects.create(
            credit_request=c1_credit,
            number=2,
            due_date=timezone.now().date() - datetime.timedelta(days=1),
            amount_due=Decimal('105000.00'),
            amount_paid=Decimal('0.00'),
            status='pending'  # check_reminders will move this to overdue
        )
        
        # Installment 3 (due in 3 days -> will trigger reminder_j3 in check_reminders)
        RepaymentScheduleItem.objects.create(
            credit_request=c1_credit,
            number=3,
            due_date=timezone.now().date() + datetime.timedelta(days=3),
            amount_due=Decimal('105000.00'),
            amount_paid=Decimal('0.00'),
            status='pending'
        )

        # Client 2: Submitted Credit Request (requires review)
        # Eligibility score should be computed on save. Since client2 is new, score will depend on registration date (0) and debt ratio
        c2_credit = CreditRequest.objects.create(
            client=client2,
            amount_requested=Decimal('100000.00'),
            duration_months=2,
            repayment_frequency='HEBDO',
            interest_rate=Decimal('5.00'),
            status='submitted'
        )

        self.stdout.write('Création du support chat...')
        # Prepopulate a chat conversation between Client 1 and Agent 1
        conv = Conversation.objects.create(
            client=client1,
            agent=agent1,
            status='open'
        )
        
        Message.objects.create(
            conversation=conv,
            sender=client1,
            content="Bonjour COFINANCE, je souhaite savoir comment payer ma prochaine échéance par Wave ?"
        )
        
        Message.objects.create(
            conversation=conv,
            sender=agent1,
            content="Bonjour Client 1, vous pouvez effectuer le transfert Wave sur notre numéro marchand 070707 et m'envoyer le reçu ici."
        )

        self.stdout.write(self.style.SUCCESS('Base de données peuplée avec succès !'))
