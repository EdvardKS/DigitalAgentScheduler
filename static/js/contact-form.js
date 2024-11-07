document.addEventListener('DOMContentLoaded', function() {
    const contactForm = document.getElementById('contactForm');
    
    if (contactForm) {
        contactForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // Get form data
            const formData = new FormData(contactForm);
            const formObject = {};
            formData.forEach((value, key) => formObject[key] = value);
            
            // Disable form while submitting
            const submitButton = contactForm.querySelector('button[type="submit"]');
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
                    // Show success message
                    const successAlert = document.createElement('div');
                    successAlert.className = 'alert alert-success mt-3';
                    successAlert.role = 'alert';
                    successAlert.innerHTML = `
                        <h4 class="alert-heading">¡Mensaje enviado con éxito!</h4>
                        <p>Gracias por contactarnos. Nos pondremos en contacto contigo pronto.</p>
                        <hr>
                        <p class="mb-0">Recibirás un correo electrónico de confirmación.</p>
                    `;
                    
                    // Insert alert before the form
                    contactForm.parentNode.insertBefore(successAlert, contactForm);
                    
                    // Reset form
                    contactForm.reset();
                    
                    // Scroll to success message
                    successAlert.scrollIntoView({ behavior: 'smooth' });
                    
                    // Remove success message after 5 seconds
                    setTimeout(() => {
                        successAlert.remove();
                    }, 5000);
                } else {
                    throw new Error(data.error || 'Error al enviar el formulario');
                }
            } catch (error) {
                // Show error message
                const errorAlert = document.createElement('div');
                errorAlert.className = 'alert alert-danger mt-3';
                errorAlert.role = 'alert';
                errorAlert.innerHTML = `
                    <h4 class="alert-heading">Error</h4>
                    <p>${error.message || 'Ha ocurrido un error al enviar el formulario. Por favor, inténtalo de nuevo.'}</p>
                `;
                
                // Insert alert before the form
                contactForm.parentNode.insertBefore(errorAlert, contactForm);
                
                // Scroll to error message
                errorAlert.scrollIntoView({ behavior: 'smooth' });
                
                // Remove error message after 5 seconds
                setTimeout(() => {
                    errorAlert.remove();
                }, 5000);
                
                console.error('Error:', error);
            } finally {
                // Re-enable submit button
                submitButton.disabled = false;
                submitButton.innerHTML = 'ENVIAR';
            }
        });

        // Add input validation
        const inputs = contactForm.querySelectorAll('input[required], textarea[required]');
        inputs.forEach(input => {
            input.addEventListener('blur', function() {
                if (!this.value.trim()) {
                    this.classList.add('is-invalid');
                } else {
                    this.classList.remove('is-invalid');
                }
            });
            
            input.addEventListener('input', function() {
                if (this.value.trim()) {
                    this.classList.remove('is-invalid');
                }
            });
        });

        // Phone number validation
        const phoneInput = contactForm.querySelector('input[name="telefono"]');
        if (phoneInput) {
            phoneInput.addEventListener('input', function() {
                this.value = this.value.replace(/[^0-9+]/g, '');
                if (this.value.length > 15) {
                    this.value = this.value.slice(0, 15);
                }
            });
        }

        // Email validation
        const emailInput = contactForm.querySelector('input[name="email"]');
        if (emailInput) {
            emailInput.addEventListener('blur', function() {
                const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailRegex.test(this.value)) {
                    this.classList.add('is-invalid');
                } else {
                    this.classList.remove('is-invalid');
                }
            });
        }
    }
});
