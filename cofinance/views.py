from django.shortcuts import render, redirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from django.contrib.auth import get_user_model, authenticate, login, logout
from django.contrib.auth.decorators import login_required

from rest_framework import status, permissions, generics, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    CreditRequest, CreditDocument, RepaymentScheduleItem, 
    Repayment, InsuranceProduct, InsurancePolicy, Notification, 
    Conversation, Message
)
from .serializers import (
    UserSerializer, UserRegisterSerializer, PasswordChangeSerializer,
    CreditRequestSerializer, RepaymentSerializer, InsuranceProductSerializer,
    InsurancePolicySerializer, NotificationSerializer, ConversationSerializer,
    MessageSerializer
)
from .permissions import IsClient, IsAgent, IsAdmin, IsAgentOrAdmin
from decimal import Decimal
import datetime

User = get_user_model()

# ==========================================
# REST API VIEWS
# ==========================================

class RegisterClientView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = (permissions.AllowAny,)


class ProfileView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            # Support updating profile custom fields
            if 'phone' in request.data:
                request.user.phone = request.data['phone']
            if 'region' in request.data:
                request.user.region = request.data['region']
            if 'monthly_income' in request.data:
                request.user.monthly_income = Decimal(str(request.data['monthly_income']))
            if 'address' in request.data:
                request.user.address = request.data['address']
            request.user.save()
            serializer = UserSerializer(request.user)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({"old_password": ["Ancien mot de passe incorrect."]}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({"detail": "Mot de passe modifié avec succès."}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CreditRequestViewSet(viewsets.ModelViewSet):
    serializer_class = CreditRequestSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if user.role in ['agent', 'admin'] or user.is_superuser:
            queryset = CreditRequest.objects.all()
            
            # Apply Filters
            region = self.request.query_params.get('region')
            status_param = self.request.query_params.get('status')
            date_param = self.request.query_params.get('date') # Format YYYY-MM-DD
            
            if region:
                queryset = queryset.filter(client__region__iexact=region)
            if status_param:
                queryset = queryset.filter(status=status_param)
            if date_param:
                queryset = queryset.filter(created_at__date=date_param)
                
            return queryset.order_by('-created_at')
        
        # Clients can only see their own requests
        return CreditRequest.objects.filter(client=user).order_by('-created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        if request.user.role != 'client':
            return Response({"detail": "Seuls les clients peuvent soumettre une demande de crédit."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[IsAgentOrAdmin])
    def transition(self, request, pk=None):
        credit = self.get_object()
        target_status = request.data.get('status')
        user = request.user
        
        valid_transitions = {
            'submitted': ['analyzing', 'rejected'],
            'analyzing': ['approved', 'rejected'],
            'approved': ['disbursed'],
            'disbursed': [],
            'rejected': []
        }
        
        current_status = credit.status
        if target_status not in valid_transitions.get(current_status, []):
            return Response({
                "detail": f"Transition de '{current_status}' vers '{target_status}' impossible ou non autorisée."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Apply workflow rules
        if target_status == 'analyzing':
            credit.assigned_agent = user
        elif target_status == 'approved':
            if user.role != 'admin' and not user.is_superuser:
                return Response({"detail": "Seuls les administrateurs peuvent approuver un crédit."}, status=status.HTTP_403_FORBIDDEN)
            credit.approved_by = user
            
        credit.status = target_status
        credit.save()
        
        return Response(CreditRequestSerializer(credit).data)


class RepaymentViewSet(viewsets.ModelViewSet):
    queryset = Repayment.objects.all().order_by('-paid_at')
    serializer_class = RepaymentSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if user.role in ['agent', 'admin'] or user.is_superuser:
            return Repayment.objects.all().order_by('-paid_at')
        return Repayment.objects.filter(schedule_item__credit_request__client=user).order_by('-paid_at')

    def create(self, request, *args, **kwargs):
        if request.user.role not in ['agent', 'admin'] and not request.user.is_superuser:
            return Response({"detail": "Seuls les agents ou les administrateurs peuvent enregistrer un remboursement."}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Save payment details
        repayment = serializer.save(recorded_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class InsuranceProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InsuranceProduct.objects.all()
    serializer_class = InsuranceProductSerializer
    permission_classes = (permissions.IsAuthenticated,)


class InsurancePolicyViewSet(viewsets.ModelViewSet):
    serializer_class = InsurancePolicySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if user.role in ['agent', 'admin'] or user.is_superuser:
            return InsurancePolicy.objects.all().order_by('-start_date')
        return InsurancePolicy.objects.filter(client=user).order_by('-start_date')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def create(self, request, *args, **kwargs):
        if request.user.role != 'client':
            return Response({"detail": "Seuls les clients peuvent souscrire à une assurance."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"detail": "Notification marquée comme lue."})


class DashboardStatsView(APIView):
    permission_classes = (IsAgentOrAdmin,)

    def get(self, request):
        # Read parameters
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        agent_id = request.query_params.get('agent_id')
        region = request.query_params.get('region')

        # Baseline filters
        credits_filter = Q()
        schedule_filter = Q()
        insurances_filter = Q()
        
        # Apply region filter (clients in region)
        if region:
            credits_filter &= Q(client__region__iexact=region)
            schedule_filter &= Q(credit_request__client__region__iexact=region)
            insurances_filter &= Q(client__region__iexact=region)

        # Apply agent filter
        if agent_id:
            credits_filter &= Q(assigned_agent_id=agent_id)
            schedule_filter &= Q(credit_request__assigned_agent_id=agent_id)

        # Apply Date Range filter on credit request created date / schedule due dates
        if start_date_str and end_date_str:
            try:
                start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
                end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
                credits_filter &= Q(created_at__date__range=(start_date, end_date))
                schedule_filter &= Q(due_date__range=(start_date, end_date))
            except ValueError:
                pass

        # 1. Volume by status
        status_counts = CreditRequest.objects.filter(credits_filter).values('status').annotate(count=Count('id'))
        status_dict = {item['status']: item['count'] for item in status_counts}
        for s in ['submitted', 'analyzing', 'approved', 'disbursed', 'rejected']:
            if s not in status_dict:
                status_dict[s] = 0

        # 2. Recovey rate = sum(amount_paid) / sum(amount_due) over the period
        sums = RepaymentScheduleItem.objects.filter(schedule_filter).aggregate(
            total_due=Sum('amount_due'),
            total_paid=Sum('amount_paid')
        )
        total_due = sums['total_due'] or Decimal('0.00')
        total_paid = sums['total_paid'] or Decimal('0.00')
        recovery_rate = (total_paid / total_due * 100) if total_due > 0 else 100.0

        # 3. Active insurance policies count
        active_insurances = InsurancePolicy.objects.filter(insurances_filter, status='active').count()

        # 4. Open chat conversations count
        open_chats = Conversation.objects.filter(status='open').count()

        data = {
            'credits_volume_by_status': status_dict,
            'recovery_rate': round(float(recovery_rate), 2),
            'total_due_in_period': float(total_due),
            'total_paid_in_period': float(total_paid),
            'active_insurances': active_insurances,
            'open_conversations': open_chats
        }
        
        return Response(data)


class SupportConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        if user.role in ['agent', 'admin'] or user.is_superuser:
            return Conversation.objects.all().order_by('-updated_at')
        return Conversation.objects.filter(client=user).order_by('-updated_at')

    def create(self, request, *args, **kwargs):
        if request.user.role != 'client':
            return Response({"detail": "Seuls les clients peuvent initier une conversation de support."}, status=status.HTTP_403_FORBIDDEN)
        
        # Check if there's already an open conversation for this client
        existing = Conversation.objects.filter(client=request.user, status='open').first()
        if existing:
            return Response(ConversationSerializer(existing).data, status=status.HTTP_200_OK)
            
        conv = Conversation.objects.create(client=request.user, status='open')
        return Response(ConversationSerializer(conv).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], permission_classes=[IsAgentOrAdmin])
    def assign(self, request, pk=None):
        conv = self.get_object()
        conv.agent = request.user
        conv.save()
        return Response(ConversationSerializer(conv).data)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conv = self.get_object()
        # Verify permissions
        if request.user.role == 'client' and conv.client != request.user:
            return Response({"detail": "Non autorisé à accéder à cette conversation."}, status=status.HTTP_403_FORBIDDEN)
            
        messages = conv.messages.all().order_by('created_at')
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)


# ==========================================
# TEMPLATE VIEWS (FRONTEND)
# ==========================================

def home_view(request):
    return render(request, 'home.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    error_msg = None
    if request.method == 'POST':
        # Simple HTML Form Authenticator
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            error_msg = "Identifiants de connexion incorrects."
            
    return render(request, 'login.html', {'error': error_msg})


def logout_view(request):
    logout(request)
    return redirect('home')


@login_required
def dashboard_view(request):
    user = request.user
    context = {}
    
    if user.role == 'client':
        # Prefill Client Dashboard Data
        credits = CreditRequest.objects.filter(client=user).order_by('-created_at')
        policies = InsurancePolicy.objects.filter(client=user).order_by('-start_date')
        insurances = InsuranceProduct.objects.all()
        notifications = Notification.objects.filter(user=user).order_by('-created_at')[:10]
        unread_notifications_count = Notification.objects.filter(user=user, is_read=False).count()
        
        # Check active chat
        active_chat = Conversation.objects.filter(client=user, status='open').first()

        context.update({
            'credits': credits,
            'policies': policies,
            'insurances': insurances,
            'notifications': notifications,
            'unread_notifications_count': unread_notifications_count,
            'active_chat': active_chat
        })
        return render(request, 'client_dashboard.html', context)
        
    else:
        # Agent or Admin Dashboard
        credits = CreditRequest.objects.all().order_by('-created_at')
        conversations = Conversation.objects.filter(status='open').order_by('-updated_at')
        agents = User.objects.filter(role='agent')
        regions = User.objects.exclude(region__isnull=True).exclude(region='').values_list('region', flat=True).distinct()
        
        context.update({
            'credits': credits,
            'conversations': conversations,
            'agents': agents,
            'regions': regions
        })
        return render(request, 'agent_dashboard.html', context)


@login_required
def chat_demo_view(request):
    """
    Demo view displaying side-by-side or tabs for Client and Agent to chat in real-time.
    """
    # Find or create a demo client conversation to chat in
    client_user = User.objects.filter(role='client').first()
    agent_user = User.objects.filter(role='agent').first() or User.objects.filter(role='admin').first()
    
    if not client_user:
        return render(request, 'chat_demo.html', {'error': "Veuillez d'abord initialiser la base de données avec seed_db."})
        
    # Get or create conversation
    conv, created = Conversation.objects.get_or_create(client=client_user, status='open')
    if not conv.agent and agent_user:
        conv.agent = agent_user
        conv.save()
        
    context = {
        'conversation': conv,
        'client_user': client_user,
        'agent_user': agent_user,
    }
    return render(request, 'chat_demo.html', context)
