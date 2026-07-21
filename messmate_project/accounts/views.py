from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.forms import PasswordResetForm
from .forms import RegisterForm
from .models import User, StudentProfile, VendorProfile, DeliveryBoyProfile
from core.email_services import send_registration_email, send_password_reset_email

def home(request):
    return render(request, 'core/home.html')

# REGISTER
def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()

            # Create specific profiles based on role
            if user.role == 'student':
                StudentProfile.objects.create(user=user)
            elif user.role == 'vendor':
                # Use default business name or extract from username
                VendorProfile.objects.create(
                    user=user, 
                    business_name=f"{user.username}'s Mess",
                    business_address=user.address or "Update Business Address",
                    contact_number=user.phone or "Update Contact"
                )
            elif user.role == 'delivery':
                DeliveryBoyProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'vehicle_number': 'Update Vehicle Number',
                        'availability_status': 'available',
                    }
                )

            verification_url = f"http://127.0.0.1:8000/verify-email/{user.id}/"
            send_registration_email(
                user_type=user.role,
                user_name=user.username,
                email=user.email,
                verification_url=verification_url,
            )
            messages.success(
                request,
                f"Registration successful! Verification email sent to {user.email}."
            )
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


# LOGIN
def user_login(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")

            # Role redirects
            if user.is_superuser or user.role == 'admin':
                return redirect('/admin/')
            elif user.role == 'vendor':
                return redirect('vendor_dashboard')
            elif user.role == 'delivery':
                return redirect('delivery_dashboard')
            else:
                return redirect('student_dashboard')
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'accounts/login.html')


# LOGOUT
def user_logout(request):
    logout(request)
    messages.success(request, "Logged out successfully.")
    return redirect('login')


# EMAIL VERIFICATION
def verify_email(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.email_verified = True
    user.save()
    messages.success(request, "Email verified successfully! You can now log in.")
    return redirect('login')


# FORGOT PASSWORD
def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get('email')
        user = User.objects.filter(email=email).first()
        if user:
            reset_url = f"http://127.0.0.1:8000/reset-password/{user.id}/"
            send_password_reset_email(user.username, user.email, reset_url)
            messages.success(request, f"Password reset instructions sent to {user.email}.")
        else:
            messages.error(request, "No account found with this email.")
    return render(request, 'accounts/forgot_password.html')


# RESET PASSWORD
def reset_password(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        new_password = request.POST.get('password')
        user.set_password(new_password)
        user.save()
        messages.success(request, "Password reset successful! Please log in.")
        return redirect('login')
    return render(request, 'accounts/reset_password.html', {'user': user})


