document.addEventListener('DOMContentLoaded', function() {
    const contactForm = document.getElementById('contactForm');
    
    if (contactForm) {
        const showAlert = (type, message, detail = '') => {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type} mt-3`;
            alertDiv.role = 'alert';
            
            let alertContent = `<h4 class="alert-heading">${message}</h4>`;
            if (detail) {
                alertContent += `<p>${detail}</p>`;
            }
            alertDiv.innerHTML = alertContent;
            
            // Remove any existing alerts
            const existingAlerts = contactForm.parentNode.querySelectorAll('.alert');
            existingAlerts.forEach(alert => alert.remove());
            
            // Insert new alert before the form
            contactForm.parentNode.insertBefore(alertDiv, contactForm);
            
            // Scroll to alert
            alertDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            // Auto-remove after 5 seconds for success messages
            if (type === 'success') {
                setTimeout(() => alertDiv.remove(), 5000);
            }
        };
        
        const handleValidationErrors = (errors) => {
            // Remove all existing validation styling
            contactForm.querySelectorAll('.is-invalid').forEach(element => {
                element.classList.remove('is-invalid');
                const feedback = element.nextElementSibling;
                if (feedback && feedback.classList.contains('invalid-feedback')) {
                    feedback.remove();
                }
            });
            
            // Add new validation styling and messages
            Object.entries(errors).forEach(([field, message]) => {
                const input = contactForm.querySelector(`[name="${field}"]`);
                if (input) {
                    input.classList.add('is-invalid');
                    
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = message;
                    input.parentNode.appendChild(feedback);
                }
            });
        };
        
        contactForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Get form data
            const formData = new FormData(contactForm);
            const formObject = {};
            formData.forEach((value, key) => formObject[key] = value);
            
            // Disable form while submitting
            const submitButton = contactForm.querySelector('button[type="submit"]');
            const originalButtonText = submitButton.innerHTML;
            submitButton.disabled = true;
            submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Enviando...';
            
            try {
                const response = await fetch('/api/contact', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formObject)
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    showAlert('success', '¡Mensaje enviado con éxito!', data.detail);
                    contactForm.reset();
                    
                    // Remove any validation styling
                    contactForm.querySelectorAll('.is-invalid').forEach(element => {
                        element.classList.remove('is-invalid');
                        const feedback = element.nextElementSibling;
                        if (feedback && feedback.classList.contains('invalid-feedback')) {
                            feedback.remove();
                        }
                    });
                } else {
                    if (data.validation_errors) {
                        handleValidationErrors(data.validation_errors);
                        showAlert('danger', 'Por favor, corrige los errores en el formulario');
                    } else {
                        throw new Error(data.error || 'Error al enviar el formulario');
                    }
                }
            } catch (error) {
                showAlert('danger', 'Error', error.message || 'Ha ocurrido un error al enviar el formulario. Por favor, inténtalo de nuevo.');
                console.error('Error:', error);
            } finally {
                // Re-enable submit button
                submitButton.disabled = false;
                submitButton.innerHTML = originalButtonText;
            }
        });

        // Real-time validation
        const validateInput = (input) => {
            const value = input.value.trim();
            const name = input.name;
            
            // Remove existing validation
            input.classList.remove('is-invalid', 'is-valid');
            const existingFeedback = input.nextElementSibling;
            if (existingFeedback && existingFeedback.classList.contains('invalid-feedback')) {
                existingFeedback.remove();
            }
            
            if (!value) {
                input.classList.add('is-invalid');
                const feedback = document.createElement('div');
                feedback.className = 'invalid-feedback';
                feedback.textContent = 'Este campo es requerido';
                input.parentNode.appendChild(feedback);
                return false;
            }
            
            if (name === 'email') {
                const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailRegex.test(value)) {
                    input.classList.add('is-invalid');
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = 'Email inválido';
                    input.parentNode.appendChild(feedback);
                    return false;
                }
            }
            
            if (name === 'telefono') {
                const phoneRegex = /^(?:\+34|0034|34)?[6789]\d{8}$/;
                if (!phoneRegex.test(value)) {
                    input.classList.add('is-invalid');
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = 'Número de teléfono inválido';
                    input.parentNode.appendChild(feedback);
                    return false;
                }
            }
            
            if (name === 'codigoPostal') {
                const postalCodeRegex = /^\d{5}$/;
                if (!postalCodeRegex.test(value)) {
                    input.classList.add('is-invalid');
                    const feedback = document.createElement('div');
                    feedback.className = 'invalid-feedback';
                    feedback.textContent = 'Código postal inválido';
                    input.parentNode.appendChild(feedback);
                    return false;
                }
            }
            
            input.classList.add('is-valid');
            return true;
        };
        
        // Add validation to all form inputs
        contactForm.querySelectorAll('input, textarea').forEach(input => {
            input.addEventListener('blur', () => validateInput(input));
            input.addEventListener('input', () => validateInput(input));
        });
    }
});
