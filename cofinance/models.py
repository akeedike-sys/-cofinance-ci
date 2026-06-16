from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from decimal import Decimal

class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Administrateur'),
        ('agent', 'Agent de terrain'),
        ('client', 'Client'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='client')
    phone = models.CharField(max_length=20, blank=True, null=True)
    region = models.CharField(max_length=50, blank=True, null=True)
    monthly_income = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, default=Decimal('0.00'))
    address = models.TextField(blank=True, null=True)
    registration_date = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class CreditRequest(models.Model):
    STATUS_CHOICES = (
        ('submitted', 'Soumise'),
        ('analyzing', 'En analyse'),
        ('approved', 'Approuvée'),
        ('disbursed', 'Décaissée'),
        ('rejected', 'Rejetée'),
    )
    FREQUENCY_CHOICES = (
        ('HEBDO', 'Hebdomadaire'),
        ('MENSUEL', 'Mensuelle'),
    )
    
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credits')
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    duration_months = models.IntegerField()
    repayment_frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('5.00'))
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='submitted')
    eligibility_score = models.IntegerField(default=0)
    assigned_agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_credits')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_credits')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Crédit #{self.id} - {self.client.username} - {self.amount_requested} FCFA ({self.get_status_display()})"

    def calculate_score(self):
        """
        Calculates credit eligibility score (0-100) based on:
        1. Repayment History (40 pts)
        2. Debt-to-Income Ratio (40 pts)
        3. Seniority (20 pts)
        """
        # 1. Repayment History (40 pts)
        # Check all installments belonging to this client due in the past or already paid
        past_installments = RepaymentScheduleItem.objects.filter(
            credit_request__client=self.client,
            due_date__lte=timezone.now().date()
        )
        
        if not past_installments.exists():
            repayment_score = Decimal('40.00')
        else:
            total = past_installments.count()
            # Paid on time: status is 'paid' and no penalties recorded
            paid_on_time = past_installments.filter(status='paid', penalties_accumulated=0).count()
            repayment_score = Decimal(str(paid_on_time)) / Decimal(str(total)) * Decimal('40.00')

        # 2. Debt-to-Income Ratio (40 pts)
        # Monthly payment = Total due / duration_months
        total_due = self.amount_requested * (1 + self.interest_rate / Decimal('100.00'))
        monthly_payment = total_due / Decimal(str(self.duration_months)) if self.duration_months else Decimal('0.00')
        
        income = self.client.monthly_income or Decimal('0.00')
        if income <= 0:
            debt_score = Decimal('0.00')
        else:
            ratio = monthly_payment / income
            debt_score = max(Decimal('0.00'), (Decimal('1.00') - ratio) * Decimal('40.00'))

        # 3. Seniority (20 pts)
        # Registration date vs Now
        reg_date = self.client.registration_date or timezone.now()
        days_active = (timezone.now() - reg_date).days
        years_active = Decimal(str(days_active)) / Decimal('365.25')
        seniority_score = min(years_active * Decimal('5.00'), Decimal('20.00'))

        self.eligibility_score = int(round(repayment_score + debt_score + seniority_score))
        return self.eligibility_score

    def generate_schedule(self):
        """
        Generates N repayment installments based on frequency and duration when approved.
        """
        # Clear existing schedule to prevent duplicates
        self.schedule.all().delete()

        total_due = self.amount_requested * (1 + self.interest_rate / Decimal('100.00'))
        
        if self.repayment_frequency == 'HEBDO':
            num_installments = self.duration_months * 4
            frequency_delta = timezone.timedelta(weeks=1)
        else:
            num_installments = self.duration_months
            frequency_delta = timezone.timedelta(days=30)
            
        if num_installments <= 0:
            return

        base_amount = (total_due / Decimal(str(num_installments))).quantize(Decimal('0.01'))
        start_date = timezone.now().date()
        
        for i in range(1, num_installments + 1):
            due_date = start_date + (frequency_delta * i)
            
            # Adjust the last installment to correct any rounding anomalies
            if i == num_installments:
                amt = total_due - (base_amount * (num_installments - 1))
            else:
                amt = base_amount
                
            RepaymentScheduleItem.objects.create(
                credit_request=self,
                number=i,
                due_date=due_date,
                amount_due=amt,
                amount_paid=Decimal('0.00'),
                status='pending'
            )

    def save(self, *args, **kwargs):
        if not self.id:
            # New request: compute score
            self.calculate_score()
        super().save(*args, **kwargs)


class CreditDocument(models.Model):
    credit_request = models.ForeignKey(CreditRequest, on_delete=models.CASCADE, related_name='documents')
    file = models.FileField(upload_to='credit_docs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Document #{self.id} for Credit #{self.credit_request_id}"


class RepaymentScheduleItem(models.Model):
    STATUS_CHOICES = (
        ('pending', 'En attente'),
        ('paid', 'Payé'),
        ('overdue', 'En retard'),
    )
    credit_request = models.ForeignKey(CreditRequest, on_delete=models.CASCADE, related_name='schedule')
    number = models.IntegerField()
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    penalties_accumulated = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    def __str__(self):
        return f"Échéance #{self.number} - Crédit #{self.credit_request_id} - Due le {self.due_date} ({self.get_status_display()})"


class Repayment(models.Model):
    schedule_item = models.ForeignKey(RepaymentScheduleItem, on_delete=models.CASCADE, related_name='repayments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_repayments')

    def __str__(self):
        return f"Remboursement #{self.id} - Montant: {self.amount} FCFA"


class InsuranceProduct(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    duration_months = models.IntegerField()
    premium = models.DecimalField(max_digits=10, decimal_places=2)
    conditions = models.TextField()

    def __str__(self):
        return self.name


class InsurancePolicy(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('expired', 'Expirée'),
    )
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='policies')
    product = models.ForeignKey(InsuranceProduct, on_delete=models.CASCADE)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')

    def __str__(self):
        return f"Police #{self.id} - {self.client.username} - {self.product.name}"

    def update_status(self):
        if self.end_date < timezone.now().date():
            self.status = 'expired'
        else:
            self.status = 'active'


class Notification(models.Model):
    EVENT_CHOICES = (
        ('credit_status', 'Changement statut crédit'),
        ('repayment_recorded', 'Remboursement enregistré'),
        ('insurance_confirmed', 'Souscription assurance confirmée'),
        ('reminder_j3', 'Rappel échéance J-3'),
        ('overdue_j1', 'Alerte retard J+1'),
        ('insurance_expiring', 'Expiration assurance proche'),
        ('chat_message', 'Nouveau message support'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification {self.event_type} pour {self.user.username}"


class Conversation(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations_as_client')
    agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations_as_agent')
    status = models.CharField(max_length=10, choices=(('open', 'Ouvert'), ('closed', 'Fermé')), default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Conversation #{self.id} - Client: {self.client.username} ({self.status})"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message #{self.id} par {self.sender.username} dans Conversation #{self.conversation_id}"
