document.addEventListener('DOMContentLoaded', () => {
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));
    const pinForm = document.getElementById('pinForm');
    const verifyPinBtn = document.getElementById('verifyPin');
    const logoutBtn = document.getElementById('logoutBtn');
    const togglePasswordBtn = document.getElementById('togglePassword');
    const passwordInput = document.getElementById('pinInput');

    // Password visibility toggle
    if (togglePasswordBtn) {
        togglePasswordBtn.addEventListener('click', () => {
            const type = passwordInput.type === 'password' ? 'text' : 'password';
            passwordInput.type = type;
            togglePasswordBtn.innerHTML = `<i data-feather="${type === 'password' ? 'eye' : 'eye-off'}"></i>`;
            feather.replace();
        });
    }

    // Password validation
    function validatePassword(password) {
        const requirements = {
            length: password.length >= 8,
            uppercase: /[A-Z]/.test(password),
            lowercase: /[a-z]/.test(password),
            number: /\d/.test(password),
            special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
        };

        if (!requirements.length) {
            return "La contraseña debe tener al menos 8 caracteres";
        }
        if (!requirements.uppercase) {
            return "La contraseña debe contener al menos una letra mayúscula";
        }
        if (!requirements.lowercase) {
            return "La contraseña debe contener al menos una letra minúscula";
        }
        if (!requirements.number) {
            return "La contraseña debe contener al menos un número";
        }
        if (!requirements.special) {
            return "La contraseña debe contener al menos un carácter especial";
        }
        
        return null;
    }

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

    function showLoginError(message) {
        const pinInput = document.getElementById('pinInput');
        pinInput.classList.add('is-invalid');
        pinInput.nextElementSibling.nextElementSibling.textContent = message;
    }

    [... rest of the file remains unchanged ...]
