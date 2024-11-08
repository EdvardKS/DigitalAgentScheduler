document.addEventListener('DOMContentLoaded', () => {
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));
    const pinForm = document.getElementById('pinForm');
    const verifyPinBtn = document.getElementById('verifyPin');
    const logoutBtn = document.getElementById('logoutBtn');
    const pinInput = document.getElementById('pinInput');
    const rememberMeCheckbox = document.getElementById('rememberMe');

    // Pagination settings
    let currentPage = 1;
    const itemsPerPage = 10;
    let filteredAppointments = [];
    let currentFilter = 'all';

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

        // Format message with remaining time if blocked
        if (isBlocked && remainingTime) {
            message = `${message}. Tiempo restante: ${remainingTime} minutos.`;
        }
        errorDiv.innerHTML = message;
        
        // Remove any existing alerts
        const existingAlerts = document.querySelectorAll('.alert');
        existingAlerts.forEach(alert => alert.remove());
        
        // Insert error message before the form
        pinForm.insertBefore(errorDiv, pinForm.firstChild);
        
        // Handle form state
        if (isBlocked) {
            // Disable all form elements when blocked
            pinInput.disabled = true;
            verifyPinBtn.disabled = true;
            rememberMeCheckbox.disabled = true;
            pinInput.value = ''; // Clear the input
        } else {
            // Enable form elements if not blocked
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

        // Don't submit if form is disabled (blocked)
        if (pinInput.disabled || verifyPinBtn.disabled) {
            return;
        }

        // Validate PIN format
        const pin = pinInput.value.trim();
        if (!pin.match(/^\d{1,11}$/)) {
            showLoginError('El PIN debe contener entre 1 y 11 dígitos numéricos');
            return;
        }

        const rememberMe = rememberMeCheckbox.checked;
        const spinner = verifyPinBtn.querySelector('.spinner-border');
        
        // Disable form and show spinner
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
            if (!pinInput.disabled) { // Only re-enable if not blocked
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
