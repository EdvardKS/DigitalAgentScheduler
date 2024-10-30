document.addEventListener('DOMContentLoaded', function() {
    const contactForm = document.getElementById('contactForm');
    
    if (contactForm) {
        contactForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(contactForm);
            const formObject = {};
            formData.forEach((value, key) => formObject[key] = value);
            
            try {
                const response = await fetch('/api/contact', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(formObject)
                });
                
                if (response.ok) {
                    alert('Tu mensaje ha sido enviado correctamente. Nos pondremos en contacto contigo pronto.');
                    contactForm.reset();
                } else {
                    throw new Error('Error al enviar el formulario');
                }
            } catch (error) {
                alert('Ha ocurrido un error al enviar el formulario. Por favor, inténtalo de nuevo.');
                console.error('Error:', error);
            }
        });
    }
});
