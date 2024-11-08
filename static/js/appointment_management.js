document.addEventListener('DOMContentLoaded', () => {
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));
    const pinForm = document.getElementById('pinForm');
    const verifyPinBtn = document.getElementById('verifyPin');
    const logoutBtn = document.getElementById('logoutBtn');
    const pinInput = document.getElementById('pinInput');
    const rememberMeCheckbox = document.getElementById('rememberMe');

    // Check for existing session
    checkSession();

    function checkSession() {
        fetch('/api/check-session')
            .then(response => response.json())
            .then(data => {
                if (data.authenticated) {
                    showDashboard();
                } else {
                    pinModal.show();
                }
            })
            .catch(error => {
                console.error('Session check error:', error);
                showLoginError('Error al verificar la sesión');
                pinModal.show();
            });
    }

    function showDashboard() {
        pinModal.hide();
        dashboardContent.style.display = 'block';
        loadAppointments();
        loadContactSubmissions();
        initializeCharts();
        feather.replace();
    }

    function showLoginError(message = 'PIN inválido', isBlocked = false, remainingTime = null) {
        const errorDiv = document.createElement('div');
        errorDiv.className = `alert alert-${isBlocked ? 'danger' : 'warning'} mt-3`;

        if (isBlocked && remainingTime) {
            message = `${message}. Tiempo restante: ${remainingTime} minutos.`;
        }
        errorDiv.innerHTML = message;
        
        const existingAlerts = document.querySelectorAll('.alert');
        existingAlerts.forEach(alert => alert.remove());
        
        pinForm.insertBefore(errorDiv, pinForm.firstChild);
        
        if (isBlocked) {
            pinInput.disabled = true;
            verifyPinBtn.disabled = true;
            rememberMeCheckbox.disabled = true;
            pinInput.value = '';
        } else {
            pinInput.disabled = false;
            verifyPinBtn.disabled = false;
            rememberMeCheckbox.disabled = false;
            pinInput.value = '';
            pinInput.focus();
        }
    }

    // PIN form submission
    pinForm.addEventListener('submit', (e) => {
        e.preventDefault();

        if (pinInput.disabled || verifyPinBtn.disabled) {
            return;
        }

        // Validate PIN length only
        const pin = pinInput.value.trim();
        if (pin.length === 0 || pin.length > 11) {
            showLoginError('El PIN debe tener entre 1 y 11 caracteres');
            return;
        }

        const rememberMe = rememberMeCheckbox.checked;
        const spinner = verifyPinBtn.querySelector('.spinner-border');
        
        verifyPinBtn.disabled = true;
        spinner.classList.remove('d-none');
        
        fetch('/api/verify-pin', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                pin: pin,
                remember_me: rememberMe
            }),
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    if (response.status === 429) {
                        throw new Error(data.error || 'Demasiados intentos fallidos');
                    }
                    throw new Error(data.error || 'Error al verificar el PIN');
                });
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                showDashboard();
            } else {
                showLoginError(data.error || 'PIN inválido');
            }
        })
        .catch(error => {
            console.error('Login error:', error);
            const errorMessage = error.message;
            const isBlocked = errorMessage.includes('Demasiados intentos');
            const remainingTime = errorMessage.match(/(\d+) minutos/);
            
            showLoginError(
                errorMessage,
                isBlocked,
                remainingTime ? parseInt(remainingTime[1]) : null
            );
        })
        .finally(() => {
            if (!pinInput.disabled) {
                verifyPinBtn.disabled = false;
                spinner.classList.add('d-none');
            }
        });
    });

    // Logout handler
    logoutBtn.addEventListener('click', () => {
        fetch('/api/logout', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    dashboardContent.style.display = 'none';
                    pinModal.show();
                }
            })
            .catch(error => {
                console.error('Logout error:', error);
                alert('Error al cerrar sesión');
            });
    });

    // Format phone number for display
    function formatPhoneNumber(phone) {
        if (!phone) return '-';
        return phone.replace(/(\d{3})(\d{3})(\d{3})/, '$1 $2 $3');
    }

    // Format date for display
    function formatDate(dateStr) {
        const date = new Date(dateStr);
        return date.toLocaleDateString('es-ES', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
});
