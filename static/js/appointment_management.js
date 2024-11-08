document.addEventListener('DOMContentLoaded', () => {
    const pinModal = new bootstrap.Modal(document.getElementById('pinModal'));
    const dashboardContent = document.getElementById('dashboardContent');
    const editModal = new bootstrap.Modal(document.getElementById('editAppointmentModal'));
    const pinForm = document.getElementById('pinForm');
    const verifyPinBtn = document.getElementById('verifyPin');
    const logoutBtn = document.getElementById('logoutBtn');
    const togglePasswordBtn = document.getElementById('togglePassword');
    const passwordInput = document.getElementById('pinInput');

    // Password validation requirements
    const requirements = {
        length: (str) => str.length >= 8,
        uppercase: (str) => /[A-Z]/.test(str),
        lowercase: (str) => /[a-z]/.test(str),
        number: (str) => /\d/.test(str),
        special: (str) => /[!@#$%^&*(),.?":{}|<>]/.test(str)
    };

    // Password visibility toggle
    if (togglePasswordBtn) {
        togglePasswordBtn.addEventListener('click', () => {
            const type = passwordInput.type === 'password' ? 'text' : 'password';
            passwordInput.type = type;
            togglePasswordBtn.innerHTML = `<i data-feather="${type === 'password' ? 'eye' : 'eye-off'}"></i>`;
            feather.replace();
        });
    }

    // Real-time password validation
    if (passwordInput) {
        passwordInput.addEventListener('input', () => {
            const password = passwordInput.value;
            validatePassword(password);
        });

        passwordInput.addEventListener('focus', () => {
            document.getElementById('passwordRequirements').style.display = 'block';
        });
    }

    function updateRequirement(requirement, valid) {
        const element = document.querySelector(`[data-requirement="${requirement}"]`);
        if (element) {
            const checkIcon = element.querySelector('.text-success');
            const xIcon = element.querySelector('.text-danger');
            
            if (valid) {
                checkIcon.classList.remove('d-none');
                xIcon.classList.add('d-none');
                element.classList.add('text-success');
                element.classList.remove('text-danger');
            } else {
                checkIcon.classList.add('d-none');
                xIcon.classList.remove('d-none');
                element.classList.add('text-danger');
                element.classList.remove('text-success');
            }
        }
    }

    function validatePassword(password) {
        let isValid = true;
        
        // Clear previous error messages
        passwordInput.classList.remove('is-invalid');
        const feedbackElement = passwordInput.nextElementSibling.nextElementSibling;
        feedbackElement.textContent = '';

        // Check each requirement
        Object.entries(requirements).forEach(([requirement, validator]) => {
            const valid = validator(password);
            updateRequirement(requirement, valid);
            if (!valid) isValid = false;
        });

        return isValid;
    }

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
        const feedbackElement = passwordInput.nextElementSibling.nextElementSibling;
        passwordInput.classList.add('is-invalid');
        feedbackElement.textContent = message;
    }

    // PIN form submission
    pinForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const password = passwordInput.value;
        const rememberMe = document.getElementById('rememberMe').checked;
        const spinner = verifyPinBtn.querySelector('.spinner-border');
        
        // Validate password
        if (!validatePassword(password)) {
            showLoginError('Por favor, cumpla con todos los requisitos de la contraseña');
            return;
        }

        // Disable form and show spinner
        verifyPinBtn.disabled = true;
        spinner.classList.remove('d-none');
        
        try {
            const response = await fetch('/api/verify-pin', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    pin: password,
                    remember_me: rememberMe
                }),
            });
            
            const data = await response.json();
            
            if (data.success) {
                showDashboard();
                passwordInput.value = '';
                // Clear validation state
                validatePassword('');
                document.getElementById('passwordRequirements').style.display = 'none';
            } else {
                showLoginError(data.error || 'Contraseña inválida');
            }
        } catch (error) {
            console.error('Login error:', error);
            showLoginError('Error al verificar la contraseña');
        } finally {
            verifyPinBtn.disabled = false;
            spinner.classList.add('d-none');
        }
    });

    // Logout handler
    logoutBtn.addEventListener('click', async () => {
        try {
            const response = await fetch('/api/logout', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                dashboardContent.style.display = 'none';
                pinModal.show();
                // Reset password input and validation state
                passwordInput.value = '';
                validatePassword('');
                document.getElementById('passwordRequirements').style.display = 'none';
            }
        } catch (error) {
            console.error('Logout error:', error);
            alert('Error al cerrar sesión');
        }
    });

    [... Rest of the file remains unchanged ...]
});
