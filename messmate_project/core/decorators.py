import os
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def vendor_required(view_func):
    @wraps(view_func)
    @login_required(login_url='login')
    def _wrapped_view(request, *args, **kwargs):
        if request.user.role != 'vendor':
            messages.error(request, 'Access Denied. Vendors only.')
            return redirect('login')
        return view_func(request, *args, **kwargs)

    return _wrapped_view
