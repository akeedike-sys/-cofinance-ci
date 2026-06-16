from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

router = DefaultRouter()
router.register(r'credits', views.CreditRequestViewSet, basename='credit')
router.register(r'repayments', views.RepaymentViewSet, basename='repayment')
router.register(r'insurances/policies', views.InsurancePolicyViewSet, basename='insurance-policy')
router.register(r'insurances/products', views.InsuranceProductViewSet, basename='insurance-product')
router.register(r'notifications', views.NotificationViewSet, basename='notification')
router.register(r'support/conversations', views.SupportConversationViewSet, basename='support-conversation')

urlpatterns = [
    # Frontend Pages
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('chat-demo/', views.chat_demo_view, name='chat_demo'),

    # API Auth endpoints
    path('api/auth/register/', views.RegisterClientView.as_view(), name='api_register'),
    path('api/auth/login/', TokenObtainPairView.as_view(), name='api_token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    
    # API Profile endpoints
    path('api/profile/', views.ProfileView.as_view(), name='api_profile'),
    path('api/profile/password/', views.ChangePasswordView.as_view(), name='api_change_password'),
    
    # API Dashboard Stats
    path('api/dashboard/stats/', views.DashboardStatsView.as_view(), name='api_dashboard_stats'),
    
    # API ViewSets
    path('api/', include(router.urls)),
]
